# -*- coding: utf-8 -*-
#
# This file is part of INGInious. See the LICENSE and the COPYRIGHTS files for
# more information about the licensing of this file.

""" LDAP plugin """
from collections import OrderedDict

# import simpleldap TODO re-add me once the PR has been accepted by devs of simpleldap
import inginious.common.customlibs.simpleldap as simpleldap  # TODO remove me once the PR has been accepted by devs of simpleldap
import logging

from inginious.frontend.webapp.user_manager import AuthMethod


class LdapAuthMethod(AuthMethod):
    """
    LDAP auth method
    """

    def __init__(self, name, host, port, encryption, require_cert, base_dn, request, prefix, mail, cn):
        if encryption not in ["none", "ssl", "tls"]:
            raise Exception("Unknown encryption method {}".format(encryption))
        if encryption == "none":
            encryption = None

        if port == 0:
            port = None

        self._logger = logging.getLogger('inginious.webapp.plugin.auth.ldap')
        self._name = name
        self._host = host
        self._port = port
        self._encryption = encryption
        self._require_cert = require_cert
        self._base_dn = base_dn
        self._request = request
        self._prefix = prefix
        self._mail = mail
        self._cn = cn

    def get_name(self):
        return self._name

    def auth(self, login_data):
        try:
            # Get configuration
            login = login_data["login"].strip().lower()
            password = login_data["password"]

            # do not send empty password to the LDAP
            if password.rstrip() == "":
                return None

            # Connect to the ldap
            self._logger.debug('Connecting to ' + self._host + ", port" + str(self._port) )
            conn = simpleldap.Connection(self._host, port=self._port, encryption=self._encryption,
                                         require_cert=self._require_cert, search_defaults={"base_dn": self._base_dn})
            self._logger.info('Connected to ' + self._host + ", port" + str(self._port) )
            request = self._request.format(login)
            user_data = conn.get(request)
            if conn.authenticate(user_data.dn, password):
                email = user_data[self._mail][0].decode('utf8')
                username = self._prefix + login
                realname = user_data[self._cn][0].decode('utf8')

                return (username, realname, email)
            else:
                self._logger.debug('Auth Failed')
                return None
        except Exception as e:
            self._logger.debug('Auth Exception:' + str(e))
            return None

    def needed_fields(self):
        return {"input": OrderedDict((("login", {"type": "text", "placeholder": "Login"}), ("password", {"type": "password", "placeholder":
            "Password"}))), "info": ""}

    def should_cache(self):
        return True

    def get_users_info(self, usernames):
        """
        :param usernames: a list of usernames
        :return: a dict containing key/pairs {username: (realname, email)} if the user is available with this auth method,
            {username: None} else
        """
        retval = {username: None for username in usernames}

        # Connect to the ldap
        try:
            conn = simpleldap.Connection(self._host, port=self._port, encryption=self._encryption,
                                         require_cert=self._require_cert, search_defaults={"base_dn": self._base_dn})
        except:
            return retval

        # Search for users
        for username in usernames:
            if username.startswith(self._prefix):
                try:
                    login = username[len(self._prefix):]
                    request = self._request.format(login)
                    user_data = conn.get(request)
                    email = user_data["mail"][0].decode('utf8')
                    realname = user_data["cn"][0].decode('utf8')

                    retval[username] = (realname, email)
                except:
                    pass

        return retval


def init(plugin_manager, _, _2, conf):
    """
        Allow to connect through a LDAP service

        Available configuration:
        ::

            {
                "plugin_module": "webapp.plugins.auth.ldap_auth",
                "host": "ldap.test.be",
                "port": 0,
                "encryption": "ssl",
                "base_dn": "o=test,c=be",
                "request": "uid={}",
                "prefix": "",
                "name": "LDAP Login",
                "require_cert": true
            }

        *host*
            The host of the ldap server
        *encryption*
            Encryption method used to connect to the LDAP server
            Can be either "none", "ssl" or "tls"
        *request*
            Request made to the server in order to find the dn of the user. The characters "{}" will be replaced by the login name.
        *prefix*
            The prefix used internally to distinguish user that have the same username on different login services
        *require_cert*
            true if a certificate is needed.
    """

    obj = LdapAuthMethod(conf.get('name', 'LDAP Login'),
                         conf.get('host', "ldap.test.be"),
                         conf.get('port', 0),
                         conf.get('encryption', "none"),
                         conf.get('require_cert', True),
                         conf.get('base_dn', ''),
                         conf.get('request', "uid={},ou=People"),
                         conf.get('prefix', ''),
                         conf.get('mail', 'mail'),
                         conf.get('cn', 'cn'))
    plugin_manager.register_auth_method(obj)
