# -*- coding: utf-8 -*-
#
# This file is part of INGInious. See the LICENSE and the COPYRIGHTS files for
# more information about the licensing of this file.
import asyncio
import logging
import uuid
from abc import abstractmethod, ABCMeta

from inginious.client._zeromq_client import BetterParanoidPirateClient
from inginious.common.messages import ClientHello, BackendUpdateContainers, BackendBatchJobDone, BackendBatchJobStarted, BackendJobStarted, \
    BackendJobDone, BackendJobSSHDebug, ClientNewBatchJob, ClientNewJob, ClientKillJob


def _callable_once(func):
    """ Returns a function that is only callable once; any other call will do nothing """

    def once(*args, **kwargs):
        if not once.called:
            once.called = True
            return func(*args, **kwargs)

    once.called = False
    return once


class AbstractClient(object, metaclass=ABCMeta):
    @abstractmethod
    def start(self):
        """ Starts the Client. Should be done after a complete initialisation of the hook manager. """
        pass

    @abstractmethod
    def close(self):
        """ Close the Client """
        pass

    @abstractmethod
    def get_batch_containers_metadata(self):
        """
            Returns the arguments needed by a particular batch container (cached version)
            :returns: a dict of dict in the form
                {
                    "container title": {
                        "container description in restructuredtext",
                        {
                            "key":
                            {
                                "type:" "file", #or "text",
                                "path": "path/to/file/inside/input/dir", #not mandatory in file, by default "key"
                                "name": "name of the field", #not mandatory in file, default "key"
                                "description": "a short description of what this field is used for", #not mandatory, default ""
                                "custom_key1": "custom_value1",
                                ...
                            }
                        }
                    }
                }
        """
        pass

    @abstractmethod
    def get_available_containers(self):
        """
        Return the list of available containers for grading
        """
        pass

    @abstractmethod
    def get_waiting_jobs_count(self):
        """Returns the total number of waiting jobs in the Client. This count is not real-time, and can be based on a local cache. """
        pass

    @abstractmethod
    def get_waiting_batch_jobs_count(self):
        """Returns the total number of waiting jobs in the Client. This count is not real-time, and can be based on a local cache. """
        pass

    @abstractmethod
    def new_job(self, task, inputdata, callback, launcher_name="Unknown", debug=False, ssh_callback=None):
        """ Add a new job. Every callback will be called once and only once.

        :type task: Task
        :param inputdata: input from the student
        :type inputdata: Storage or dict
        :param callback: a function that will be called asynchronously in the client's process, with the results.
            it's signature must be (result, grade, problems, tests, custom, archive), where:
            result is itself a tuple containing the result string and the main feedback (i.e. ('success', 'You succeeded');
            grade is a number between 0 and 100 indicating the grade of the users;
            problems is a dict of tuple, in the form {'problemid': result};
            test is a dict of tests made in the container
            custom is a dict containing random things set in the container
            archive is either None or a bytes containing a tgz archive of files from the job
        :type callback: __builtin__.function or __builtin__.instancemethod
        :param launcher_name: for informational use
        :type launcher_name: str
        :param debug: Either True(outputs more info), False(default), or "ssh" (starts a remote ssh server. ssh_callback needs to be defined)
        :type debug: bool or string
        :param ssh_callback: a callback function that will be called with (host, port, password), the needed credentials to connect to the
                             remote ssh server. May be called with host, port, password being None, meaning no session was open.
        :type ssh_callback: __builtin__.function or __builtin__.instancemethod or None
        :return: the new job id
        """
        pass

    @abstractmethod
    def new_batch_job(self, container_name, inputdata, callback, launcher_name="Unknown"):
        """ Add a new batch job. callback is a function that will be called asynchronously in the client's process.
            inputdata is a dict containing all the keys of get_batch_containers_metadata()[container_name]["parameters"].
            The values associated are file-like objects for "file" types and  strings for "text" types.
        """
        pass

    @abstractmethod
    def kill_job(self, job_id):
        """
        Kills a running job
        :param job_id:
        """
        pass


class Client(BetterParanoidPirateClient):
    def __init__(self, context, backend_addr):
        super().__init__(context, backend_addr)
        self._logger = logging.getLogger("inginious.client")
        self._available_containers = []
        self._available_batch_containers = []

        self._register_handler(BackendUpdateContainers, self._handle_update_containers)
        self._register_transaction(ClientNewBatchJob, BackendBatchJobDone, self._handle_batch_job_done, self._handle_batch_job_abort,
                                   lambda x: x.job_id, [
                                       (BackendBatchJobStarted, self._handle_batch_job_started)
                                   ])
        self._register_transaction(ClientNewJob, BackendJobDone, self._handle_job_done, self._handle_job_abort,
                                   lambda x: x.job_id, [
                                       (BackendJobStarted, self._handle_job_started),
                                       (BackendJobSSHDebug, self._handle_job_ssh_debug)
                                   ])

    async def _handle_update_containers(self, message: BackendUpdateContainers):
        self._available_batch_containers = message.available_batch_containers
        self._available_containers = message.available_containers
        self._logger.info("Updated containers and batch containers")
        self._logger.debug("Containers: %s", str(self._available_containers))
        self._logger.debug("Batch containers: %s", str(self._available_batch_containers))

    async def _handle_batch_job_started(self, message: BackendBatchJobStarted, **kwargs):
        self._logger.debug("Batch job %s started", message.job_id)

    async def _handle_batch_job_done(self, message: BackendBatchJobDone, callback):
        self._logger.debug("Batch job %s done", message.job_id)

        # Call the callback
        try:
            callback(message.retval, message.stdout, message.stderr, message.file)
        except Exception as e:
            self._logger.exception("Failed to call the callback function for jobid {}: {}".format(message.job_id, repr(e)), exc_info=True)

    async def _handle_job_started(self, message: BackendJobStarted, **kwargs):
        self._logger.debug("Job %s started", message.job_id)

    async def _handle_job_done(self, message: BackendJobDone, task, callback, ssh_callback):
        self._logger.debug("Job %s done", message.job_id)
        job_id = message.job_id

        # Ensure ssh_callback is called at least once
        try:
            # NB: original ssh_callback was wrapped with _callable_once
            await self._loop.run_in_executor(None, lambda: ssh_callback(None, None, None))
        except:
            self._logger.exception("Error occured while calling ssh_callback for job %s", job_id)

        # Call the callback
        try:
            callback(message.result, message.grade, message.problems, message.tests, message.custom, message.archive)
        except Exception as e:
            self._logger.exception("Failed to call the callback function for jobid {}: {}".format(job_id, repr(e)), exc_info=True)

    async def _handle_job_ssh_debug(self, message: BackendJobSSHDebug, ssh_callback, **kwargs):
        try:
            await self._loop.run_in_executor(None, lambda: ssh_callback(message.host, message.port, message.password))
        except:
            self._logger.exception("Error occured while calling ssh_callback for job %s", message.job_id)

    async def _handle_batch_job_abort(self, job_id: str, callback):
        await self._handle_batch_job_done(BackendBatchJobDone(job_id, -1, "Backend unavailable, retry later", "", None), callback)

    async def _handle_job_abort(self, job_id: str, task, callback, ssh_callback):
        await self._handle_job_done(BackendJobDone(job_id, ("crash", "Backend unavailable, retry later"), 0.0, {}, {}, {}, None), task, callback,
                                    ssh_callback)

    async def _on_disconnect(self):
        self._logger.warning("Disconnected from backend, retrying...")

    async def _on_connect(self):
        self._available_containers = []
        self._available_batch_containers = []
        await self._simple_send(ClientHello("me"))
        self._logger.info("Connecting to backend")

    def start(self):
        """ Starts the Client. Should be done after a complete initialisation of the hook manager. """
        self._loop.call_soon_threadsafe(asyncio.ensure_future, self.client_start())

    def close(self):
        """ Close the Client """
        pass

    def get_batch_containers_metadata(self):
        """
            Returns the arguments needed by a particular batch container (cached version)
            :returns: a dict of dict in the form
                {
                    "container title": {
                        "container description in restructuredtext",
                        {
                            "key":
                            {
                                "type:" "file", #or "text",
                                "path": "path/to/file/inside/input/dir", #not mandatory in file, by default "key"
                                "name": "name of the field", #not mandatory in file, default "key"
                                "description": "a short description of what this field is used for", #not mandatory, default ""
                                "custom_key1": "custom_value1",
                                ...
                            }
                        }
                    }
                }
        """
        return self._available_batch_containers

    def get_available_containers(self):
        """
        Return the list of available containers for grading
        """
        return self._available_containers

    def get_waiting_jobs_count(self):
        """Returns the total number of waiting jobs in the Client. This count is not real-time, and can be based on a local cache. """
        # TODO
        return 0

    def get_waiting_batch_jobs_count(self):
        """Returns the total number of waiting jobs in the Client. This count is not real-time, and can be based on a local cache. """
        # TODO
        return 0

    def new_job(self, task, inputdata, callback, launcher_name="Unknown", debug=False, ssh_callback=None):
        """ Add a new job. Every callback will be called once and only once.

        :type task: Task
        :param inputdata: input from the student
        :type inputdata: Storage or dict
        :param callback: a function that will be called asynchronously in the client's process, with the results.
            it's signature must be (result, grade, problems, tests, custom, archive), where:
            result is itself a tuple containing the result string and the main feedback (i.e. ('success', 'You succeeded');
            grade is a number between 0 and 100 indicating the grade of the users;
            problems is a dict of tuple, in the form {'problemid': result};
            test is a dict of tests made in the container
            custom is a dict containing random things set in the container
            archive is either None or a bytes containing a tgz archive of files from the job
        :type callback: __builtin__.function or __builtin__.instancemethod
        :param launcher_name: for informational use
        :type launcher_name: str
        :param debug: Either True(outputs more info), False(default), or "ssh" (starts a remote ssh server. ssh_callback needs to be defined)
        :type debug: bool or string
        :param ssh_callback: a callback function that will be called with (host, port, password), the needed credentials to connect to the
                             remote ssh server. May be called with host, port, password being None, meaning no session was open.
        :type ssh_callback: __builtin__.function or __builtin__.instancemethod or None
        :return: the new job id
        """
        job_id = str(uuid.uuid4())

        if debug == "ssh" and ssh_callback is None:
            self._logger.error("SSH callback not set in %s/%s", task.get_course_id(), task.get_id())
            callback(("crash", "SSH callback not set."), 0.0, {}, {}, {}, None)
            return
        # wrap ssh_callback to ensure it is called at most once, and that it can always be called to simplify code
        ssh_callback = _callable_once(ssh_callback if ssh_callback is not None else lambda _1, _2, _3: None)

        environment = task.get_environment()
        if environment not in self._available_containers:
            self._logger.warning("Env %s not available for task %s/%s", environment, task.get_course_id(), task.get_id())
            ssh_callback(None, None, None)  # ssh_callback must be called once
            callback(("crash", "Environment not available."), 0.0, {}, {}, {}, None)
            return

        enable_network = task.allow_network_access_grading()

        try:
            limits = task.get_limits()
            time_limit = int(limits.get('time', 20))
            hard_time_limit = int(limits.get('time_hard', 3 * time_limit))
            mem_limit = int(limits.get('memory', 200))
        except:
            self._logger.exception("Cannot retrieve limits for task %s/%s", task.get_course_id(), task.get_id())
            ssh_callback(None, None, None)  # ssh_callback must be called once
            callback(("crash", "Error while reading task limits"), 0.0, {}, {}, {}, None)
            return

        msg = ClientNewJob(job_id, task.get_course_id(), task.get_id(), inputdata, environment, enable_network, time_limit,
                           hard_time_limit, mem_limit, debug, launcher_name)
        self._loop.call_soon_threadsafe(asyncio.ensure_future, self._create_transaction(msg, task=task, callback=callback,
                                                                                        ssh_callback=ssh_callback))

        return job_id

    def new_batch_job(self, container_name, inputdata, callback, launcher_name="Unknown"):
        """ Add a new batch job. callback is a function that will be called asynchronously in the client's process.
            inputdata is a dict containing all the keys of get_batch_containers_metadata()[container_name]["parameters"].
            The values associated are file-like objects for "file" types and  strings for "text" types.
        """
        job_id = str(uuid.uuid4())

        # Verify inputdata
        if container_name not in self._available_batch_containers:
            raise Exception("Invalid container")

        batch_args = self._available_batch_containers[container_name]["parameters"]
        if set(inputdata.keys()) != set(batch_args.keys()):
            raise Exception("Invalid keys for inputdata")
        for key in batch_args:
            if batch_args[key]["type"] == "text" and not isinstance(inputdata[key], str):
                raise Exception("Invalid value for inputdata: the value for key {} should be a string".format(key))
            elif batch_args[key]["type"] == "file" and isinstance(inputdata[key], str):
                raise Exception("Invalid value for inputdata: the value for key {} should be a file object".format(key))

        msg = ClientNewBatchJob(job_id, container_name, inputdata, launcher_name)
        self._loop.call_soon_threadsafe(asyncio.ensure_future, self._create_transaction(msg, callback=callback))

        return job_id

    def kill_job(self, job_id):
        """
        Kills a running job
        """
        self._loop.call_soon_threadsafe(asyncio.ensure_future, self._simple_send(ClientKillJob(job_id)))
