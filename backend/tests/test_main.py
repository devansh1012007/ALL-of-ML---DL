from fastapi.testclient import TestClient

from backend.app.main import app


def test_get_ml_models():
    with TestClient(app) as client:
        response = client.get("/api/v1/ml/models")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


def test_get_datasets():
    with TestClient(app) as client:
        response = client.get("/api/v1/ml/datasets")
        assert response.status_code == 200
        payload = response.json()
        assert isinstance(payload, dict)
        assert "datasets" in payload


def test_train_invalid_dataset():
    with TestClient(app) as client:
        payload = {
            "model_name": "Logistic_Regression",
            "dataset_name": "missing_dataset.csv",
            "label_column": "label",
            "test_size": 0.2,
            "random_state": 42,
            "hyperparameters": {},
            "mode": "manual",
        }
        response = client.post("/api/v1/ml/train", json=payload)
        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower() or "could not parse" in response.json()["detail"].lower()
