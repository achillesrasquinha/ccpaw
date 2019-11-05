# imports - standard imports
import collections
import random

# imports - third-party imports
import requests

# imports - module imports
from cc.util.types  import (
    sequencify,
    squash,
    merge_dict
)
from cc.util.string import (
    sanitize_html,
    sanitize_text,
    lower
)
from cc.exception   import (
    ValueError,
    TypeError,
    ResponseError,
    JSONDecodeError,
    AuthenticationError,
    HTTPError
)
from cc.config      import DEFAULT
from cc.log         import get_logger
from cc.exception   import (
    TypeError
)

logger = get_logger()

class Client:
    """
    The :class:`Client` class provides a convenient access to the Cell 
    Collective API. Instances of this class are a gateway to interacting 
    with Cell Collective's API through the CCPy.

    :param base_url: A base URL to use.
    :param proxies: A dictionary/list of proxies to use. If a list is passed,
        each element in the list should be a dictionary of the format 
        ``{ protocol: ip }``.
    :param test: Attempt to test the connection to the base url.

    Usage::

        >>> import cc
        >>> client = cc.Client()
        >>> client
        <Client url='https://cellcollective.org'>
    """
    def __init__(self,
        base_url = DEFAULT["URL"],
        proxies  = [ ],
        test     = True
    ):
        self.base_url    = base_url
        self._auth_token = None
        self._session    = requests.Session()

        if proxies and \
            not isinstance(proxies, (collections.Mapping, list, tuple)):
            raise TypeError((
                "proxies %s are not of valid type. You must "
                "either a dictionary of a list of dictionaries of the "
                "following format { protocol: ip }."))

        if isinstance(proxies, collections.Mapping):
            proxies = [proxies]

        self._proxies = proxies

        if test:
            self.ping()

    def __repr__(self):
        repr_ = "<Client url='%s'>" % (self.base_url)
        return repr_

    def _build_url(self, *args, **kwargs):
        prefix = kwargs.get("prefix", True)
        parts  = [ ]

        if prefix:
            parts.append(self.base_url)

        url = "/".join(map(str, parts + args))

        return url

    def _request(self, method, url, *args, **kwargs):
        raise_error = kwargs.pop("raise_error", True)
        token       = kwargs.pop("token",       None)
        headers     = kwargs.pop("headers",     { })
        proxies     = kwargs.pop("proxies",     self._proxies)
        data        = kwargs.get("params",      kwargs.get("data"))
        prefix      = kwargs.get("prefix",      True)

        headers.update({
            "User-Agent": USER_AGENT
        })

        if token:
            headers.update({
                HEADER_AUTHENTICATION: token
            })
        else:
            if self._auth_token:
                headers.update({
                    HEADER_AUTHENTICATION: self._auth_token
                })

        if proxies:
            proxies = random.choice(proxies)
            logger.info("Using proxy %s to dispatch request." % proxies)

        if prefix:
            url = self._build_url(url)

        logger.info("Dispatching a %s request to URL: %s with Arguments - %s" \
            % (method, url, kwargs))
        response = self._session.request(method, url,
            headers = headers, proxies = proxies, *args, **kwargs)

        if not response.ok and raise_error:
            if response.text:
                logger.error("Error recieved from the server: %s" % response.text)

            response.raise_for_status()

        return response

    def post(self, url, *args, **kwargs):
        """
        Dispatch a POST request to the server.

        :param url: URL part (does not include the base URL).
        :param args: Arguments provided to ``client._request``
        :param kwargs: Keyword Arguments provided to ``client._request``

        Usage::

            >>> import cc
            >>> client   = cc.Client()
            >>> response = client.post("api/module/12345/report")
            >>> response.content
            b'"First Name","Last Name","Email","Institution","Last Updated Date"\n'
        """
        response = self._request("POST", url, *args, **kwargs)
        return response

    def ping(self, *args, **kwargs):
        """
        Check if the URL is alive.

        :param args: Arguments provided to ``client._request``
        :param kwargs: Keyword Arguments provided to ``client._request``

        Usage::

            >>> import cc
            >>> client = cc.Client()
            >>> client.ping()
            'pong'
        """
        response = self._request("GET", "api/ping", *args, **kwargs)
        try:
            content = response.json()
            if content.get("data") == "pong":
                return "pong"
            else:
                raise ValueError("Unable to ping to URL %s." % self.base_url)
        except JSONDecodeError:
            raise ResponseError("Unable to decode JSON.")

    def auth(self, *args, **kwargs):
        """
        Authenticate client.

        Usage::

            >>> import cc
            >>> client = cc.Client()
            >>> client.auth(
                    email    = "test@cellcollective.org",
                    password = "test"
                )
            >>> client.authenticated
            True

            >>> client.auth(token = "<YOUR_AUTH_TOKEN>")
            >>> client.authenticated
            True
        """
        token = kwargs.get("token", None)

        if not token:
            email    = kwargs.get("email",    None)
            password = kwargs.get("password", None)

            if not email:
                raise ValueError("email not provided.")

            if not password:
                raise ValueError("password not provided.")

            data = dict(username = email, password = password)
            response   = self.post("_api/login", data = data)
            auth_token = response.headers.get(HEADER_AUTHENTICATION)

            if auth_token:
                self._auth_token = auth_token
            else:
                raise AuthenticationError(_AUTHENTICATION_ERROR_STRING)
        else:
            try:
                self.me(token = token)
                self._auth_token = token
            except HTTPError:
                raise AuthenticationError(_AUTHENTICATION_ERROR_STRING)

    def logout(self):
        """
        Logout client.
        """
        self._auth_token = None

    @property
    def authenticated(self):
        _authenticated = bool(self._auth_token)
        return _authenticated

    def raise_for_authentication(self):
        """
        Raise AuthenticationError in case the client hasn't been authenticated.
        """
        
        if not self.authenticated:
            raise AuthenticationError("Client is not authenticated.")  

    def me(self, *args, **kwargs):
        """
        Get the user profile of the authenticated client.

        Usage::

            >>> import cc
            >>> client = cc.Client()
            >>> client.auth(email = "test@cellcollective.org", password = "test")
            >>> client.me()
            <User id=10887 name='Test Test'>
        """
        response = self._request("GET", "_api/user/getProfile", *args, **kwargs)
        content  = response.json()
        user     = _user_response_object_to_user_object(self, content)

        return user

    def get(self, resource, *args, **kwargs):
        """
        Get resources.

        :param resource: Resource name.
        """

        _resource = resource.lower()
        resources = [ ]

        id_       = kwargs.get("id")
        query     = kwargs.get("query")

        size      = min(
            kwargs.get("size", DEFAULT["MAX_API_RESOURCE_FETCH"]),
            DEFAULT["MAX_API_RESOURCE_FETCH"]
        )
        since     = kwargs.get("since", 1)

        if id_:
            if isinstance(id_, str) and id_.isdigit():
                id_ = int(id_)
            id_ = sequencify(id_)

        if   _resource == "model":
            url     = self._build_url("_api","model","get", prefix = False)
            params  = None

            version = kwargs.get("version")
            hash_   = kwargs.get("hash_")

            if id_:
                url = self._build_url(url, str(id_[0]), prefix = False)

                if version:
                    params = {
                        "version": str(version) + ("&%s" % hash_ if hash_ else "")
                    }

            if query:
                url     = self._build_url(url, prefix = False)
                params  = [
                    ("search", "species"),
                    ("search", "knowledge"),
                    ("name",   query)
                ]

            response = self._request("GET", url, params = params)
            content  = response.json()
            
            if id_:
                resources = QueryList([
                    _model_version_response_object_to_model_object(self, content)
                ])
            else:
                content   = content[since - 1 : since - 1 + size]
                resources = QueryList([
                    _model_response_object_to_model_object(self, obj)
                        for obj in content
                ])
        elif _resource == "user":
            if not id_:
                raise ValueError("id required.")

            response    = self._request("GET", "_api/user/lookupUsers",
                params = [("id", i) for i in id_]
            )
            content     = response.json()

            for user_id, user_data in content.items():
                user = _user_response_object_to_user_object(self, 
                    merge_dict({ "id": user_id }, user_data)
                )
                resources.append(user)

        return squash(resources)

    def read(self, filename, save = False):
        """
        Read an SBML file.

        :param filename: Name of the file locally present to read an SBML file.
        """

        files       = dict({
            "upload": (filename, open(filename, "rb"))
        })

        response    = self.post("_api/model/import", files = files)
        content     = response.json()

        model       = _model_version_response_object_to_model_object(self,
            content)

        return model

    def search(self, resource, query, *args, **kwargs):
        """
        Search a resource.

        :param resource: Name of the resource.
        :param query: Search a query string.
        """
        return self.get(resource, query = query, *args, **kwargs)