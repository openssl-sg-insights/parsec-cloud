use pyo3::{
    import_exception, once_cell::GILOnceCell, pyclass, pymethods, IntoPy, PyAny, PyObject,
    PyResult, Python,
};
use std::future::Future;
use tokio::task::JoinHandle;

import_exception!(trio, RunFinishedError);

// We have one global Tokio runtime that is lazily initialized

struct Stuff {
    tokio_runtime: tokio::runtime::Runtime,
    // Cache Python function to save time when we need them
    // Stuff needed when we will have to wake up the trio coroutine. Note we do as much work
    // has possible now given we can turn error into Python exception, while we will have to
    // raise a Rust panic! in the code waking up trio (given error there means we cannot reach Python !)
    trio_current_trio_token_fn: PyObject,
    trio_reschedule_fn: PyObject,
    trio_current_task_fn: PyObject,
    trio_wait_task_rescheduled: PyObject,
    trio_abort_succeeded: PyObject,
    outcome_value_fn: PyObject,
    outcome_error_fn: PyObject,
}

static STUFF: GILOnceCell<PyResult<Stuff>> = GILOnceCell::new();

fn get_stuff(py: Python<'_>) -> PyResult<&Stuff> {
    let res = STUFF.get_or_init(py, || {
        let trio_lowlevel = py.import("trio")?.getattr("lowlevel")?;
        let outcome = py.import("outcome")?;

        Ok(Stuff {
            tokio_runtime: tokio::runtime::Runtime::new()?,
            trio_current_trio_token_fn: trio_lowlevel.getattr("current_trio_token")?.into_py(py),
            trio_reschedule_fn: trio_lowlevel.getattr("reschedule")?.into_py(py),
            trio_current_task_fn: trio_lowlevel.getattr("current_task")?.into_py(py),
            trio_wait_task_rescheduled: trio_lowlevel.getattr("wait_task_rescheduled")?.into_py(py),
            trio_abort_succeeded: trio_lowlevel
                .getattr("Abort")?
                .getattr("SUCCEEDED")?
                .into_py(py),
            outcome_value_fn: outcome.getattr("Value")?.into_py(py),
            outcome_error_fn: outcome.getattr("Error")?.into_py(py),
        })
    });
    match res {
        Ok(stuff) => Ok(stuff),
        Err(err) => Err(err.clone_ref(py)),
    }
}

#[pyclass]
struct TokioTaskAborterFromTrio {
    handle: JoinHandle<()>,
    task: PyObject,
}

#[pymethods]
impl TokioTaskAborterFromTrio {
    fn __call__(&self, py: Python, _raise_cancel: &PyAny) -> PyResult<PyObject> {
        // Given we return `trio.lowlevel.Abort.SUCCEEDED` we have given our word to
        // trio we won't call reschedule for this task
        // So we store the aborted information in the `task.custom_sleep_data` attribute
        // that trio has designed for us just for this kind of need \^^/
        // Also note the GIL makes our life easy here: given we hold it during the whole
        // "read `custom_sleep_data` then call reschedule if needed", we cannot have
        // concurrency issues when modifying `custom_sleep_data`.
        self.task.setattr(py, "custom_sleep_data", true)?;
        self.handle.abort();
        Ok(get_stuff(py)?.trio_abort_succeeded.clone())
    }
}

pub(crate) fn spawn_future_into_trio_coroutine<F, T>(py: Python, fut: F) -> PyResult<&PyAny>
where
    F: Future<Output = PyResult<T>> + Send + 'static,
    T: IntoPy<PyObject>,
{
    let stuff = get_stuff(py)?;
    let trio_token = stuff.trio_current_trio_token_fn.call0(py)?;
    let trio_reschedule_fn = stuff.trio_reschedule_fn.clone();
    let outcome_value_fn = stuff.outcome_value_fn.clone();
    let outcome_error_fn = stuff.outcome_error_fn.clone();

    let trio_current_task = stuff.trio_current_task_fn.call0(py)?;
    let trio_current_task2 = trio_current_task.clone();

    // Schedule the Tokio future
    let handle = stuff.tokio_runtime.spawn(async move {
        // Here we have left the trio thread and are inside a thread provided by the Tokio runtime

        // Actual run of the Tokio future
        let ret = fut.await;

        // Now that our job is done we have to call trio's reschedule function and
        // pass it the result as an outcome object

        Python::with_gil(|py| {
            let trio_current_task = trio_current_task.as_ref(py);

            // Special case if trio has already cancelled the coroutine
            let aborted = trio_current_task.getattr("custom_sleep_data").expect("Cannot access `<task>.custom_sleep_data`");
            if aborted.is_true().expect("Cannot evaluate `<task>.custom_sleep_data`") {
                return
            }

            // Create the outcome object
            let outcome = match ret {
                Ok(val) => {
                    outcome_value_fn.call1(py, (val, )).expect("Cannot create `outcome.Value(<result>)`")
                },
                Err(err) =>  {
                    outcome_error_fn.call1(py, (err, )).expect("Cannot create `outcome.Error(<result>)`")
                },
            };

            // Reschedule the coroutine, this must be done from within the trio thread so we have to use
            // the trio token to schedule a synchronous function that will do the actual schedule call
            match trio_token.call_method1(
                py, "run_sync_soon", (trio_reschedule_fn.as_ref(py), trio_current_task, outcome)
            ) {
                Ok(_) => (),
                // We can ignore the error if the trio loop has been closed...
                Err(err) if err.is_instance_of::<RunFinishedError>(py)  => (),
                // ...but for any other exception there is not much we can do :'(
                Err(err) => {
                    panic!("Cannot call `TrioToken.run_sync_soon(trio.lowlevel.reschedule, <outcome>)`: {:?}", err);
                }
            }
        })
    });

    // This aborter is callback that will be called by trio if our coroutine gets
    // cancelled, this allow us to cancel the related tokio task
    let aborter = TokioTaskAborterFromTrio {
        handle,
        task: trio_current_task2,
    };

    // Return the special coroutine object that tells trio loop to block our task
    // until it is manually rescheduled
    stuff
        .trio_wait_task_rescheduled
        .as_ref(py)
        .call1((aborter,))
}