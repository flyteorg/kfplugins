from __future__ import absolute_import

try:
    from inspect import getfullargspec as _getargspec
except ImportError:
    from inspect import getargspec as _getargspec

import os as _os
import sys as _sys
import six as _six
import datetime as _datetime
from flytekit.common import constants as _constants
from flytekit.common.exceptions import scopes as _exception_scopes
from flytekit.common.tasks import output as _task_output, sdk_runnable as _sdk_runnable
from flytekit.common.types import helpers as _type_helpers
from flytekit.models import literals as _literal_models, task as _task_models
from tfoperatorplugin.sdk.models import task as _tfjob_model
from google.protobuf.json_format import MessageToDict as _MessageToDict


TFJOB_TASK_TYPE = "tfjob"

class SdkTFJobTask(_sdk_runnable.SdkRunnableTask):
    """
    This class includes the additional logic for building a task that executes as a Spark Job.

    """
    def __init__(
            self,
            task_function,
            task_type,
            discovery_version,
            retries,
            deprecated,
            discoverable,
            timeout,
            image,
            num_ps,
            replicas,
            command,
            args,
            volumeClaimName,
            environment
    ):
        """
        :param task_function: Function container user code.  This will be executed via the SDK's engine.
        :param Text task_type: string describing the task type
        :param Text discovery_version: string describing the version for task discovery purposes
        :param int retries: Number of retries to attempt
        :param Text deprecated:
        :param bool discoverable:
        :param datetime.timedelta timeout:
        :param dict[Text, Text] spark_conf:
        :param dict[Text, Text] hadoop_conf:
        :param dict[Text, Text] environment: [optional] environment variables to set when executing this task.
        """
        tfjob = _tfjob_model.TFJob(
            image=image,
            num_ps=num_ps,
            replicas=replicas,
            command=command,
            args=args,
            volumeClaimName=volumeClaimName,
        ).to_flyte_idl()
        super(SdkTFJobTask, self).__init__(
            task_function,
            task_type,
            discovery_version,
            retries,
            deprecated,
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            discoverable,
            timeout,
            environment,
            _MessageToDict(tfjob),
        )

    @_exception_scopes.system_entry_point
    def execute(self, inputs):
        """
        :param flytekit.models.literals.LiteralMap inputs:
        :rtype: dict[Text, flytekit.models.common.FlyteIdlEntity]
        :returns: This function must return a dictionary mapping 'filenames' to Flyte Interface Entities.  These
            entities will be used by the engine to pass data from node to node, populate metadata, etc. etc..  Each
            engine will have different behavior.  For instance, the Flyte engine will upload the entities to a remote
            working directory (with the names provided), which will in turn allow Flyte Propeller to push along the
            workflow.  Where as local engine will merely feed the outputs directly into the next node.
        """
        inputs_dict = _type_helpers.unpack_literal_map_to_sdk_python_std(inputs, {
            k: _type_helpers.get_sdk_type_from_literal_type(v.type) for k, v in _six.iteritems(self.interface.inputs)
        })
        outputs_dict = {
            name: _task_output.OutputReference(_type_helpers.get_sdk_type_from_literal_type(variable.type))
            for name, variable in _six.iteritems(self.interface.outputs)
        }

        inputs_dict.update(outputs_dict)

        
        _exception_scopes.user_entry_point(self.task_function)(
            **inputs_dict
        )
        return {
            _constants.OUTPUT_FILE_NAME: _literal_models.LiteralMap(
                literals={k: v.sdk_value for k, v in _six.iteritems(outputs_dict)}
            )
        }

    def _get_kwarg_inputs(self):
        # Trim off first parameter as it is reserved for workflow_parameters
        return set(_getargspec(self.task_function).args[1:])


def tf_job_task(
        _task_function=None,
        cache_version='',
        retries=0,
        deprecated='',
        cache=False,
        timeout=None,
        image='',
        num_ps=1,
        replicas=1,
        command='',
        args=dict(),
        volumeClaimName='tfjob-claim',
        environment=None,
        cls=None
):
    """
    Decorator to create a spark task.  This task will connect to a Spark cluster, configure the environment,
    and then execute the code within the _task_function as the Spark driver program.

    .. code-block:: python

        @inputs(a=Types.Integer)
        @spark_task(
            spark_conf={
                    'spark.executor.cores': '7',
                    'spark.executor.instances': '31',
                    'spark.executor.memory': '32G'
                }
            )
        def sparky(wf_params, spark_context, a):
            pass

    :param _task_function: this is the decorated method and shouldn't be declared explicitly.  The function must
        take a first argument, and then named arguments matching those defined in @inputs and @outputs.  No keyword
        arguments are allowed for wrapped task functions.
    :param Text cache_version: [optional] string representing logical version for discovery.  This field should be
        updated whenever the underlying algorithm changes.

        .. note::

            This argument is required to be a non-empty string if `cache` is True.

    :param int retries: [optional] integer determining number of times task can be retried on
        :py:exc:`flytekit.sdk.exceptions.RecoverableException` or transient platform failures.  Defaults
        to 0.

        .. note::

            If retries > 0, the task must be able to recover from any remote state created within the user code.  It is
            strongly recommended that tasks are written to be idempotent.

    :param Text deprecated: [optional] string that should be provided if this task is deprecated.  The string
        will be logged as a warning so it should contain information regarding how to update to a newer task.
    :param bool cache: [optional] boolean describing if the outputs of this task should be cached and
        re-usable.
    :param datetime.timedelta timeout: [optional] describes how long the task should be allowed to
        run at max before triggering a retry (if retries are enabled).  By default, tasks are allowed to run
        indefinitely.  If a null timedelta is passed (i.e. timedelta(seconds=0)), the task will not timeout.
    :param dict[Text,Text] spark_conf: A definition of key-value pairs for spark config for the job.
    :param dict[Text,Text] hadoop_conf: A definition of key-value pairs for hadoop config for the job.
    :param dict[Text,Text] environment: [optional] environment variables to set when executing this task.
    :param cls: This can be used to override the task implementation with a user-defined extension. The class
        provided must be a subclass of flytekit.common.tasks.sdk_runnable.SdkRunnableTask.  Generally, it should be a
        subclass of flytekit.common.tasks.spark_task.SdkSparkTask.  A user can use this parameter to inject bespoke
        logic into the base Flyte programming model.
    :rtype: flytekit.common.tasks.sdk_runnable.SdkRunnableTask
    """

    def wrapper(fn):
        return (cls or SdkTFJobTask)(
            task_function=fn,
            task_type=TFJOB_TASK_TYPE,
            discovery_version=cache_version,
            retries=retries,
            deprecated=deprecated,
            discoverable=cache,
            timeout=timeout or _datetime.timedelta(seconds=0),
            image=image or {},
            num_ps=num_ps or {},
            replicas=replicas or {},
            command=command or {},
            args=args or {},
            volumeClaimName=volumeClaimName or {},
            environment=environment or {},
        )

    if _task_function:
        return wrapper(_task_function)
    else:
        return wrapper
