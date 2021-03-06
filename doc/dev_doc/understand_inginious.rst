Understand INGInious
====================

INGInious is made from three different packages:

- The :doc:`common` which contains basic blocks, like *tasks* and
  *courses*. Derivates from this blocks are created by the frontend and other modules.
  The :doc:`common` does not need the :doc:`backend` nor the :doc:`frontend`;
- The :doc:`agent`, that runs jobs. It interacts directly with Docker to start new containers, and send the grades back to the backend.
  A specific part of the :doc:`backend` is in charge of starting the agents automatically; you most of time won't need to it manually.
  The agent needs to be run *on* the Docker host, as it interacts with other containers with Unix sockets, and must also interact with CGroups
  to allow a very fine management of timeouts and memory limits.
- The :doc:`backend`, which is in charge of handling grading requests, giving the work to distant agents;
  the backend is made to be simple and frontend-agnostic; you can 'easily' replace the frontend by something else.
  The backend only store information about *running* tasks. This point is important when considering replication and horizontal scalability (see
  later)
- The :doc:`frontend` which is a web interface for the backend. It provides a simple yet powerful interface for students and teachers.
  It is made to be "stateless": all its state is stored in DB, allowing to replicate the frontend horizontally.

Basic architecture of INGInious
-------------------------------
The following schema shows the basic architecture of INGInious:

.. image:: /dev_doc/inginious_arch.png
    :align: center

Scalability of Docker hosts
---------------------------
In order to share the work between multiple servers, INGInious can use multiple agents, as shown in the following schema.
The completely horizontal scalability is (nearly) without additionnal configuration, and can be made fully automatic with a bit of work.

.. image:: /dev_doc/inginious_arch_docker.png
    :align: center

Scalability of the INGInious frontend
-------------------------------------
As the backend only store information about *running* submission, and the frontend is stateless, we can use the replication feature of MongoDB to
scale horizontally the frontends too. The (final) schema below show the most advanced way of configuring INGInious, with multiple frontends
replicated and multiple docker hosts.

.. image:: /dev_doc/inginious_arch_full.png
    :align: center

Grading containers and student containers
-----------------------------------------

A *grading container* is a container that do the grading. It typically runs a script made by a teacher or its assistants, a launch sub-containers,
called *student containers*, that will separately jail code made by students.

A single *grading container* can launch more than one *student container*; the interaction between the two is completely secured by the agent.

Jobs
----

When you send a student's input to the backend, it creates what we call a *job*.
Jobs are sent to an object called the *Client*, which itself is a simple communication layer to a job queue that we call the *Backend*.
The *Backend* itself can be used by multiple *Client*s, and dispatch jobs among *Agent*s, which can be of different types (for now, we have two
kind of agents, *DockerAgent* and *MCQAgent*)

When a job is submitted, a callback must be given: it is automatically called when the task is done, asynchronously.

Submission
----------

A submission is an extension of the concept of job. A submission only exists in the
frontend, and it is mainly a job saved to db.