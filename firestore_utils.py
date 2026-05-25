import json
import requests

class FirestoreClient:
    """
    A lightweight Firestore client utilizing the native REST API.
    """
    def __init__(self, project_id, api_key=None):
        self.project_id = project_id
        self.api_key = api_key
        self.base_url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents"

    def _get_url(self, path=None, doc_id=None, params=None, action=None):
        url = self.base_url
        if path:
            url += f"/{path}"
        if doc_id:
            url += f"/{doc_id}"
        if action:
            url += f":{action}"

        query_params = []
        if self.api_key:
            query_params.append(f"key={self.api_key}")
        if params:
            for k, v in params.items():
                if isinstance(v, list):
                    for val in v:
                        query_params.append(f"{k}={val}")
                else:
                    query_params.append(f"{k}={v}")

        if query_params:
            url += "?" + "&".join(query_params)
        return url

    def _to_firestore_value(self, val):
        if isinstance(val, str):
            return {"stringValue": val}
        elif isinstance(val, bool):
            return {"booleanValue": val}
        elif isinstance(val, (int, float)):
            if isinstance(val, float):
                return {"doubleValue": val}
            return {"integerValue": str(val)}
        elif isinstance(val, list):
            return {"arrayValue": {"values": [self._to_firestore_value(v) for v in val]}}
        elif isinstance(val, dict):
            return {"mapValue": {"fields": {k: self._to_firestore_value(v) for k, v in val.items()}}}
        elif val is None:
            return {"nullValue": None}
        return {"stringValue": str(val)}

    def _from_firestore_value(self, value_dict):
        if "stringValue" in value_dict:
            return value_dict["stringValue"]
        elif "booleanValue" in value_dict:
            return value_dict["booleanValue"]
        elif "integerValue" in value_dict:
            return int(value_dict["integerValue"])
        elif "doubleValue" in value_dict:
            return float(value_dict["doubleValue"])
        elif "arrayValue" in value_dict:
            values = value_dict["arrayValue"].get("values", [])
            return [self._from_firestore_value(v) for v in values]
        elif "mapValue" in value_dict:
            fields = value_dict["mapValue"].get("fields", {})
            return {k: self._from_firestore_value(v) for k, v in fields.items()}
        elif "nullValue" in value_dict:
            return None
        return None

    def _to_firestore_doc(self, py_dict):
        return {"fields": {k: self._to_firestore_value(v) for k, v in py_dict.items()}}

    def _from_firestore_doc(self, doc_dict):
        fields = doc_dict.get("fields", {})
        return {k: self._from_firestore_value(v) for k, v in fields.items()}

    def save_document(self, path, doc_id, data, merge=False):
        params = {}
        if merge:
            params["updateMask.fieldPaths"] = list(data.keys())

        url = self._get_url(path, doc_id, params)
        doc_data = self._to_firestore_doc(data)
        try:
            response = requests.patch(url, json=doc_data, timeout=10)
            return response.status_code in [200, 201]
        except Exception as e:
            print(f"[Firestore Error] Save failed: {e}")
            return False

    def get_document(self, path, doc_id):
        url = self._get_url(path, doc_id)
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return self._from_firestore_doc(response.json())
            return None
        except Exception as e:
            print(f"[Firestore Error] Get failed: {e}")
            return None

    def query_documents(self, collection_path, field, op, value):
        # The parent path is everything before the last collectionId
        parts = collection_path.split('/')
        collection_id = parts[-1]
        parent_path = "/".join(parts[:-1]) if len(parts) > 1 else None

        url = self._get_url(path=parent_path, action="runQuery")

        query = {
            "structuredQuery": {
                "from": [{"collectionId": collection_id}],
                "where": {
                    "fieldFilter": {
                        "field": {"fieldPath": field},
                        "op": op,
                        "value": self._to_firestore_value(value)
                    }
                }
            }
        }
        try:
            response = requests.post(url, json=query, timeout=15)
            if response.status_code == 200:
                results = response.json()
                docs = []
                # runQuery returns a list of results, each can have a "document"
                if isinstance(results, list):
                    for res in results:
                        if "document" in res:
                            doc = self._from_firestore_doc(res["document"])
                            name = res["document"]["name"]
                            doc["_id"] = name.split("/")[-1]
                            docs.append(doc)
                return docs
            else:
                print(f"[Firestore Error] Query failed ({response.status_code}): {response.text}")
                return None # Return None to indicate error
        except Exception as e:
            print(f"[Firestore Error] Query failed: {e}")
            return None
