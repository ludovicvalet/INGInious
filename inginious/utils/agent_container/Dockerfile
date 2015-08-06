# Download the sources of the agent from github and build the container from it.

FROM centos

RUN \
    yum -y update && \
    yum -y install epel-release && \
    yum -y install docker python-pip gcc python-devel git && \
    pip install pytidylib docutils rpyc cgroup-utils pyyaml

# temp workaround for Docker 1.7 (TODO: revert me!)
RUN \
    git clone https://github.com/GuillaumeDerval/docker-py.git /docker-py && \
    cd /docker-py && \
    pip install . && \
    cd .. && \
    rm -Rf /docker-py
    
VOLUME /agent_volume
VOLUME /sys/fs/cgroup

RUN \
    mkdir /agent && \
    mkdir /agent/backend && \
    touch /agent/backend/__init__.py && \
    git clone https://github.com/UCL-INGI/INGInious.git /INGInious && \
    cp -r /INGInious/common /agent/common && \
    cp -r /INGInious/backend/agent /agent/backend/agent && \
    rm -rf /INGInious

WORKDIR /agent
CMD ["/agent/backend/agent/start_container_agent.py"]

LABEL agent-version=0.3