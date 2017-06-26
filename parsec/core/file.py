import json
import sys

from cryptography.hazmat.backends.openssl import backend as openssl
from cryptography.hazmat.primitives import hashes

from parsec.crypto import generate_sym_key, load_sym_key
from parsec.exceptions import BlockNotFound, FileError, VlobNotFound
from parsec.tools import from_jsonb64, to_jsonb64


class File:

    @classmethod
    async def create(cls, synchronizer):
        self = File()
        self.synchronizer = synchronizer
        blob = [await self._build_file_blocks(b'')]
        blob = json.dumps(blob)
        blob = blob.encode()
        self.encryptor = generate_sym_key()
        encrypted_blob = self.encryptor.encrypt(blob)
        encrypted_blob = to_jsonb64(encrypted_blob)
        vlob = await self.synchronizer.vlob_create(encrypted_blob)
        self.id = vlob['id']
        self.read_trust_seed = vlob['read_trust_seed']
        self.write_trust_seed = vlob['write_trust_seed']
        self.version = 0
        self.dirty = False
        return self

    @classmethod
    async def load(cls, synchronizer, id, key, read_trust_seed, write_trust_seed, version=None):
        self = File()
        self.synchronizer = synchronizer
        self.id = id
        self.read_trust_seed = read_trust_seed
        self.write_trust_seed = write_trust_seed
        self.encryptor = load_sym_key(from_jsonb64(key))
        vlob = await self.synchronizer.vlob_read(self.id, self.read_trust_seed, version)
        self.version = vlob['version']
        self.dirty = False
        if vlob['id'] in await self.synchronizer.vlob_list():
            self.version -= 1
            self.dirty = True
        return self

    async def get_vlob(self):
        vlob = {}
        vlob['id'] = self.id
        vlob['read_trust_seed'] = self.read_trust_seed
        vlob['write_trust_seed'] = self.write_trust_seed
        vlob['key'] = to_jsonb64(self.encryptor.key)
        return vlob

    async def get_blocks(self):
        version = await self.get_version()
        vlob = await self.synchronizer.vlob_read(self.id, self.read_trust_seed, version)
        encrypted_blob = from_jsonb64(vlob['blob'])
        blob = self.encryptor.decrypt(encrypted_blob)
        blob = json.loads(blob.decode())
        block_ids = []
        for block_and_key in blob:
            for block in block_and_key['blocks']:
                block_ids.append(block['block'])
        return block_ids

    async def get_version(self):
        return self.version + 1 if self.dirty else self.version

    async def read(self, size=None, offset=0):
        version = await self.get_version()
        vlob = await self.synchronizer.vlob_read(self.id, self.read_trust_seed, version)
        encrypted_blob = from_jsonb64(vlob['blob'])
        blob = self.encryptor.decrypt(encrypted_blob)
        blob = json.loads(blob.decode())
        # Get data
        matching_blocks = await self._find_matching_blocks(size, offset)
        data = matching_blocks['pre_included_data']
        for blocks_and_key in matching_blocks['included_blocks']:
            block_key = blocks_and_key['key']
            decoded_block_key = from_jsonb64(block_key)
            encryptor = load_sym_key(decoded_block_key)
            for block_properties in blocks_and_key['blocks']:
                block = await self.synchronizer.block_read(block_properties['block'])
                # Decrypt
                block_content = from_jsonb64(block['content'])
                chunk_data = encryptor.decrypt(block_content)
                # Check integrity
                digest = hashes.Hash(hashes.SHA512(), backend=openssl)
                digest.update(chunk_data)
                new_digest = digest.finalize()
                assert new_digest == from_jsonb64(block_properties['digest'])
                data += chunk_data
        data += matching_blocks['post_included_data']
        return data

    async def write(self, data, offset):
        previous_blocks = await self._find_matching_blocks()
        previous_blocks_ids = []
        for blocks_and_key in previous_blocks['included_blocks']:
            for block_properties in blocks_and_key['blocks']:
                previous_blocks_ids.append(block_properties['block'])
        matching_blocks = await self._find_matching_blocks(len(data), offset)
        new_data = matching_blocks['pre_excluded_data']
        new_data += data
        new_data += matching_blocks['post_excluded_data']
        blob = []
        blob += matching_blocks['pre_excluded_blocks']
        blob.append(await self._build_file_blocks(new_data))
        blob += matching_blocks['post_excluded_blocks']
        blob = json.dumps(blob)
        blob = blob.encode()
        encrypted_blob = self.encryptor.encrypt(blob)
        encrypted_blob = to_jsonb64(encrypted_blob)
        await self.synchronizer.vlob_update(self.id,
                                            self.version + 1,
                                            self.write_trust_seed,
                                            encrypted_blob)
        current_blocks = await self._find_matching_blocks()
        current_blocks_ids = []
        for blocks_and_key in current_blocks['included_blocks']:
            for block_properties in blocks_and_key['blocks']:
                current_blocks_ids.append(block_properties['block'])
        for block_id in previous_blocks_ids:
            if block_id not in current_blocks_ids:
                try:
                    await self.synchronizer.block_delete(block_id)
                except BlockNotFound:
                    pass
        self.dirty = True

    async def truncate(self, length):
        previous_blocks = await self._find_matching_blocks()
        previous_blocks_ids = []
        for blocks_and_key in previous_blocks['included_blocks']:
            for block_properties in blocks_and_key['blocks']:
                previous_blocks_ids.append(block_properties['block'])
        matching_blocks = await self._find_matching_blocks(length, 0)
        blob = []
        blob += matching_blocks['included_blocks']
        blob.append(await self._build_file_blocks(matching_blocks['post_included_data']))
        blob = json.dumps(blob)
        blob = blob.encode()
        encrypted_blob = self.encryptor.encrypt(blob)
        encrypted_blob = to_jsonb64(encrypted_blob)
        await self.synchronizer.vlob_update(self.id,
                                            self.version + 1,
                                            self.write_trust_seed,
                                            encrypted_blob)
        current_blocks = await self._find_matching_blocks()
        current_blocks_ids = []
        for blocks_and_key in current_blocks['included_blocks']:
            for block_properties in blocks_and_key['blocks']:
                current_blocks_ids.append(block_properties['block'])
        for block_id in previous_blocks_ids:
            if block_id not in current_blocks_ids:
                try:
                    await self.synchronizer.block_delete(block_id)
                except BlockNotFound:
                    pass
        self.dirty = True

    async def stat(self):
        version = await self.get_version()
        vlob = await self.synchronizer.vlob_read(self.id,
                                                 self.read_trust_seed,
                                                 version)
        encrypted_blob = vlob['blob']
        encrypted_blob = from_jsonb64(encrypted_blob)
        blob = self.encryptor.decrypt(encrypted_blob)
        blob = json.loads(blob.decode())
        # TODO which block index? Or add date in vlob_service ?
        block_stat = await self.synchronizer.block_stat(id=blob[-1]['blocks'][-1]['block'])
        size = 0
        for blocks_and_key in blob:
            for block in blocks_and_key['blocks']:
                size += block['size']
        # TODO: don't provide atime field if we don't know it?
        return {
            'id': self.id,
            'type': 'file',
            'created': block_stat['creation_date'],
            'updated': block_stat['creation_date'],
            'size': size,
            'version': vlob['version']
        }

    # async def history(self):
    #     # TODO ?
    #     pass

    async def restore(self, version=None):
        if version is None:
            version = self.version - 1 if self.version > 1 else 1
        if version > 0 and version < await self.get_version():
            await self.discard()
            vlob = await self.synchronizer.vlob_read(self.id, self.read_trust_seed, version)
            await self.synchronizer.vlob_update(self.id,
                                                self.version + 1,
                                                self.write_trust_seed,
                                                vlob['blob'])
        elif version < 1 or version > self.version:
            raise FileError('bad_version', 'Bad version number.')
        self.dirty = True

    async def reencrypt(self):
        old_vlob = await self.synchronizer.vlob_read(self.id, self.read_trust_seed, self.version)
        old_blob = old_vlob['blob']
        old_encrypted_blob = from_jsonb64(old_blob)
        new_blob = self.encryptor.decrypt(old_encrypted_blob)
        self.encryptor = generate_sym_key()
        new_encrypted_blob = self.encryptor.encrypt(new_blob)
        new_encrypted_blob = to_jsonb64(new_encrypted_blob)
        new_vlob = await self.synchronizer.vlob_create(new_encrypted_blob)
        self.id = new_vlob['id']
        self.read_trust_seed = new_vlob['read_trust_seed']
        self.write_trust_seed = new_vlob['write_trust_seed']
        self.dirty = True

    async def commit(self):
        block_ids = await self.get_blocks()
        for block_id in block_ids:
            await self.synchronizer.block_synchronize(block_id)
        new_vlob = await self.synchronizer.vlob_synchronize(self.id)
        if new_vlob:
            if new_vlob is not True:
                self.id = new_vlob['id']
                self.read_trust_seed = new_vlob['read_trust_seed']
                self.write_trust_seed = new_vlob['write_trust_seed']
                new_vlob = await self.get_vlob()
            self.version += 1
        self.dirty = False
        return new_vlob

    async def discard(self):
        already_synchronized = False
        block_ids = await self.get_blocks()
        for block_id in block_ids:
            try:
                await self.synchronizer.block_delete(block_id)
            except BlockNotFound:
                already_synchronized = True
        try:
            await self.synchronizer.vlob_delete(self.id)
        except VlobNotFound:
            already_synchronized = True
        self.dirty = False
        return not already_synchronized

    async def _build_file_blocks(self, data):
        if isinstance(data, str):
            data = data.encode()
        # Create chunks
        chunk_size = 4096  # TODO modify size
        chunks = [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]
        # Force a chunk even if the data is empty
        if not chunks:
            chunks = [b'']
        encryptor = generate_sym_key()
        blocks = []
        for chunk in chunks:
            # Digest
            digest = hashes.Hash(hashes.SHA512(), backend=openssl)
            digest.update(chunk)
            chunk_digest = digest.finalize()  # TODO replace with hexdigest ?
            chunk_digest = to_jsonb64(chunk_digest)
            # Encrypt block
            cypher_chunk = encryptor.encrypt(chunk)
            # Store block
            cypher_chunk = to_jsonb64(cypher_chunk)
            block_id = await self.synchronizer.block_create(content=cypher_chunk)
            blocks.append({'block': block_id,
                           'digest': chunk_digest,
                           'size': len(chunk)})
        # New vlob atom
        block_key = to_jsonb64(encryptor.key)
        blob = {'blocks': blocks,
                'key': block_key}
        self.dirty = True
        return blob

    async def _find_matching_blocks(self, size=None, offset=0):
        if size is None:
            size = sys.maxsize
        pre_excluded_blocks = []
        post_excluded_blocks = []
        version = await self.get_version()
        vlob = await self.synchronizer.vlob_read(self.id,
                                                 self.read_trust_seed,
                                                 version)
        blob = vlob['blob']
        encrypted_blob = from_jsonb64(blob)
        blob = self.encryptor.decrypt(encrypted_blob)
        blob = json.loads(blob.decode())
        pre_excluded_blocks = []
        included_blocks = []
        post_excluded_blocks = []
        cursor = 0
        pre_excluded_data = b''
        pre_included_data = b''
        post_included_data = b''
        post_excluded_data = b''
        for blocks_and_key in blob:
            block_key = blocks_and_key['key']
            decoded_block_key = from_jsonb64(block_key)
            encryptor = load_sym_key(decoded_block_key)
            for block_properties in blocks_and_key['blocks']:
                cursor += block_properties['size']
                if cursor <= offset:
                    if len(pre_excluded_blocks) and pre_excluded_blocks[-1]['key'] == block_key:
                        pre_excluded_blocks[-1]['blocks'].append(block_properties)
                    else:
                        pre_excluded_blocks.append({'blocks': [block_properties], 'key': block_key})
                elif cursor > offset and cursor - block_properties['size'] < offset:
                    delta = cursor - offset
                    block = await self.synchronizer.block_read(block_properties['block'])
                    content = from_jsonb64(block['content'])
                    block_data = encryptor.decrypt(content)
                    pre_excluded_data = block_data[:-delta]
                    pre_included_data = block_data[-delta:][:size]
                    if size < len(block_data[-delta:]):
                        post_excluded_data = block_data[-delta:][size:]
                elif cursor > offset and cursor <= offset + size:
                    if len(included_blocks) and included_blocks[-1]['key'] == block_key:
                        included_blocks[-1]['blocks'].append(block_properties)
                    else:
                        included_blocks.append({'blocks': [block_properties], 'key': block_key})
                elif cursor > offset + size and cursor - block_properties['size'] < offset + size:
                    delta = offset + size - (cursor - block_properties['size'])
                    block = await self.synchronizer.block_read(block_properties['block'])
                    content = from_jsonb64(block['content'])
                    block_data = encryptor.decrypt(content)
                    post_included_data = block_data[:delta]
                    post_excluded_data = block_data[delta:]
                else:
                    if len(post_excluded_blocks) and post_excluded_blocks[-1]['key'] == block_key:
                        post_excluded_blocks[-1]['blocks'].append(block_properties)
                    else:
                        post_excluded_blocks.append({'blocks': [block_properties],
                                                     'key': block_key})
        return {
            'pre_excluded_blocks': pre_excluded_blocks,
            'pre_excluded_data': pre_excluded_data,
            'pre_included_data': pre_included_data,
            'included_blocks': included_blocks,
            'post_included_data': post_included_data,
            'post_excluded_data': post_excluded_data,
            'post_excluded_blocks': post_excluded_blocks
        }
