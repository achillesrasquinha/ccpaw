# imports - standard imports
import datetime as dt
import collections

# imports - third-party imports
import requests

# imports - module imports
from cc.util.types import (
    sequencify,
    squash,
    merge_dict
)
from cc.exception  import (
    ValueError,
    AuthenticationError
)
from cc.constant   import (
    DEFAULT_URL,
    HEADER_AUTHENTICATION,
    USER_AGENT,
    MAXIMUM_API_RESOURCE_FETCH
)
from cc.model      import (
    Model,
    BooleanModel, Species,
    User
)
from cc.log        import get_logger

logger = get_logger()

def _cc_datetime_to_python_datetime(datetime_):
    datetime_object = dt.datetime.strptime(
        datetime_,
        "%a, %d %b %Y %H:%M:%S %Z"
    )
    return datetime_object

def _model_get_by_id_response_object_to_model_object(client, response):
    _, data             = next(iter(response.items()))

    model               = BooleanModel()

    if "score" in data:
        model.score = data["score"]["score"]

    model.species       = [
        Species(
            id_     = id_,
            name    = species_data["name"],
            created = _cc_datetime_to_python_datetime(
                species_data["creationDate"]
            ) if species_data.get("creationDate") else None,
            updated = _cc_datetime_to_python_datetime(
                species_data["updateDate"]
            ) if species_data.get("updateDate")   else None,
        ) for id_, species_data in data["speciesMap"].items()
    ]

    return model

def _model_get_response_object_to_model_object(client, response):
    data                = response["model"]

    model               = Model()

    model.id            = data["id"]
    model.name          = data["name"]
    model.description   = data["description"]
    model.author        = data["author"]
    model.tags          = data["tags"] and data["tags"].split(", ")
    
    model.created       = _cc_datetime_to_python_datetime(
        data["creationDate"]
    ) if data["creationDate"] else None

    model.updated       = dict(
        biologic        = 
            _cc_datetime_to_python_datetime(
                data["biologicUpdateDate"]
            ) if data["biologicUpdateDate"] else None,
        knowledge       =
            _cc_datetime_to_python_datetime(
                data["knowledgeBaseUpdateDate"]
            ) if data["knowledgeBaseUpdateDate"] else None,
    )

    model.user          = client.get("user", id_ = data["userId"])
    model.public        = data["published"]

    model.versions      = [
        client.get("model",
            id_     = model.id,
            version = version,
            hash_   = data.get("hash")
        ) for version in data["modelVersionMap"].keys()
    ]

    return model

def _user_get_profile_response_object_to_user_object(response):
    user             = User()

    user.id          = response["id"]
    user.email       = response.get("email")
    user.first_name  = response["firstName"]
    user.last_name   = response["lastName"]
    user.institution = response.get("institution")

    return user

class Client:
    def __init__(self, base_url = DEFAULT_URL, proxies = [ ]):
        self.base_url       = base_url
        self._session       = requests.Session()
        self._proxies       = proxies
        self._auth_token    = None

    def _build_url(self, *args, **kwargs):
        prefix = kwargs.get("prefix", True)
        parts  = [ ]

        if prefix:
            parts.append(self.base_url)

        url = "/".join([*parts, *args])

        return url

    def _request(self, method, url, *args, **kwargs):
        raise_error     = kwargs.pop("raise_error", True)
        headers         = kwargs.pop("headers", { })
        proxies         = kwargs.pop("proxies", self._proxies)
        data            = kwargs.get("params", kwargs.get("data"))

        if self._auth_token:
            headers.update({
                "User-Agent": USER_AGENT,
                HEADER_AUTHENTICATION: self._auth_token
            })

        logger.info("Dispatching a %s Request to URL: %s with Arguments - %s" \
            % (method, url, kwargs))
        response        = self._session.request(method, url,
            headers = headers, proxies = proxies, *args, **kwargs)

        if not response.ok and raise_error:
            if response.text:
                logger.error("Error recieved from the server: %s" % response.text)

            response.raise_for_status()

        return response

    def auth(self, *args, **kwargs):
        email           = kwargs.get("email",    None)
        password        = kwargs.get("password", None)

        if not email:
            raise ValueError("email not provided.")

        if not password:
            raise ValueError("password not provided.")

        url             = self._build_url("_api", "login")
        data            = dict(
            username    = email,
            password    = password
        )
        response        = self._request("POST", url, data = data)
        
        auth_token      = response.headers.get(HEADER_AUTHENTICATION)

        if auth_token:
            self._auth_token    = auth_token

            url                 = self._build_url("_api", "user", "getProfile")
            response            = self._request("GET", url)
            
            content             = response.json()

            self.profile        = _user_get_profile_response_object_to_user_object(content)
        else:
            raise AuthenticationError("Unable to login into Cell Collective \
                with credentials provided.")

    @property
    def authenticated(self):
        _authenticated = bool(self._auth_token)
        return _authenticated

    def get(self, resource, *args, **kwargs):
        _resource   = resource.lower()
        resources   = [ ]

        id_         = kwargs.get("id_")

        size        = min(
            kwargs.get("size", MAXIMUM_API_RESOURCE_FETCH),
            MAXIMUM_API_RESOURCE_FETCH
        )
        since       = kwargs.get("since", 1)

        if id_:
            if isinstance(id_, str) and id_.isdigit():
                id_ = int(id_)

            id_ = sequencify(id_)

        if   _resource == "model":
            url     = self._build_url("_api", "model", "get")
            params  = None

            version = kwargs.get("version")
            hash_   = kwargs.get("hash_")

            if id_:
                url = self._build_url(url, str(id_[0]), prefix = False)

                if version:
                    params = { "version": str(version) + ("&%s" % hash_ if hash_ else "") }

            response    = self._request("GET", url, params = params)
            content     = response.json()

            if id_:
                resources = [
                    _model_get_by_id_response_object_to_model_object(self, content)
                ]
            else:
                content   = content[since - 1 : since - 1 + size]
                resources = [
                    _model_get_response_object_to_model_object(self, obj)
                        for obj in content
                ]
        elif _resource == "user":
            if not id_:
                raise ValueError("id required.")

            url         = self._build_url("_api", "user", "lookupUsers")
            response    = self._request("GET", url,
                params = [("id", i) for i in id_]
            )

            content     = response.json()

            for user_id, user_data in content.items():
                user = _user_get_profile_response_object_to_user_object(
                    merge_dict({ "id": user_id }, user_data)
                )
                resources.append(user)

        return squash(resources)

    def read(self, filename, save = False):
        url         = self._build_url("_api", "model", "import")
        
        files       = dict({
            "upload": (filename, open(filename, "rb"))
        })

        response    = self._request("POST", url, files = files)

        content     = response.json()

        model       = _model_get_by_id_response_object_to_model_object(self,
            content)

        return model