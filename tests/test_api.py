import json


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestGradeEndpointHappyPath:
    def test_valid_request_returns_200(self, client, valid_form_fields, valid_image_bytes, auth_headers):
        response = client.post(
            "/api/grade",
            data=valid_form_fields,
            files={"sheet_image": ("sheet.jpg", valid_image_bytes, "image/jpeg")},
        headers=auth_headers,
        )
        assert response.status_code == 200

    def test_response_matches_evaluation_schema(self, client, valid_form_fields, valid_image_bytes, auth_headers):
        response = client.post(
            "/api/grade",
            data=valid_form_fields,
            files={"sheet_image": ("sheet.jpg", valid_image_bytes, "image/jpeg")},
        headers=auth_headers,
        )
        body = response.json()
        for field in [
            "question_number", "criteria", "total_awarded", "total_max",
            "grade", "overall_feedback", "transcription", "low_confidence",
        ]:
            assert field in body, f"missing field: {field}"

    def test_response_carries_through_question_number(self, client, valid_form_fields, valid_image_bytes, auth_headers):
        fields = {**valid_form_fields, "question_number": "7c"}
        response = client.post(
            "/api/grade",
            data=fields,
            files={"sheet_image": ("sheet.jpg", valid_image_bytes, "image/jpeg")},
        headers=auth_headers,
        )
        assert response.json()["question_number"] == "7c"

    def test_criteria_have_evidence_and_reason(self, client, valid_form_fields, valid_image_bytes, auth_headers):
        response = client.post(
            "/api/grade",
            data=valid_form_fields,
            files={"sheet_image": ("sheet.jpg", valid_image_bytes, "image/jpeg")},
        headers=auth_headers,
        )
        for criterion in response.json()["criteria"]:
            assert criterion["evidence"]
            assert criterion["reason"]

    def test_totals_are_internally_consistent(self, client, valid_form_fields, valid_image_bytes, auth_headers):
        response = client.post(
            "/api/grade",
            data=valid_form_fields,
            files={"sheet_image": ("sheet.jpg", valid_image_bytes, "image/jpeg")},
        headers=auth_headers,
        )
        body = response.json()
        computed = sum(c["awarded"] for c in body["criteria"])
        assert abs(computed - body["total_awarded"]) < 0.01


class TestAuthentication:
    def test_missing_api_key_returns_401(self, client, valid_form_fields, valid_image_bytes):
        response = client.post(
            "/api/grade",
            data=valid_form_fields,
            files={"sheet_image": ("sheet.jpg", valid_image_bytes, "image/jpeg")},
        )
        assert response.status_code == 401

    def test_wrong_api_key_returns_401(self, client, valid_form_fields, valid_image_bytes):
        response = client.post(
            "/api/grade",
            data=valid_form_fields,
            files={"sheet_image": ("sheet.jpg", valid_image_bytes, "image/jpeg")},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 401

    def test_health_does_not_require_auth(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200


class TestGradeEndpointErrorPaths:
    def test_missing_all_fields_returns_422(self, client, auth_headers):
        response = client.post("/api/grade", headers=auth_headers)
        assert response.status_code == 422

    def test_missing_image_returns_422(self, client, valid_form_fields, auth_headers):
        response = client.post("/api/grade", data=valid_form_fields, headers=auth_headers)
        assert response.status_code == 422

    def test_missing_question_text_returns_422(self, client, valid_form_fields, valid_image_bytes, auth_headers):
        fields = {k: v for k, v in valid_form_fields.items() if k != "question_text"}
        response = client.post(
            "/api/grade",
            data=fields,
            files={"sheet_image": ("sheet.jpg", valid_image_bytes, "image/jpeg")},
        headers=auth_headers,
        )
        assert response.status_code == 422

    def test_invalid_rubric_json_returns_400(self, client, valid_form_fields, valid_image_bytes, auth_headers):
        fields = {**valid_form_fields, "rubric_json": "not valid json"}
        response = client.post(
            "/api/grade",
            data=fields,
            files={"sheet_image": ("sheet.jpg", valid_image_bytes, "image/jpeg")},
        headers=auth_headers,
        )
        assert response.status_code == 400
        assert response.json()["error"] == "InvalidImageError"

    def test_empty_rubric_array_returns_422(self, client, valid_form_fields, valid_image_bytes, auth_headers):
        fields = {**valid_form_fields, "rubric_json": "[]"}
        response = client.post(
            "/api/grade",
            data=fields,
            files={"sheet_image": ("sheet.jpg", valid_image_bytes, "image/jpeg")},
        headers=auth_headers,
        )
        assert response.status_code == 422

    def test_non_image_file_returns_400(self, client, valid_form_fields, auth_headers):
        response = client.post(
            "/api/grade",
            data=valid_form_fields,
            files={"sheet_image": ("notes.txt", b"plain text content", "text/plain")},
        headers=auth_headers,
        )
        assert response.status_code == 400
        assert response.json()["error"] == "InvalidImageError"

    def test_empty_image_file_returns_400(self, client, valid_form_fields, auth_headers):
        response = client.post(
            "/api/grade",
            data=valid_form_fields,
            files={"sheet_image": ("sheet.jpg", b"", "image/jpeg")},
        headers=auth_headers,
        )
        assert response.status_code == 400

    def test_oversized_image_returns_413(self, client, valid_form_fields, monkeypatch, auth_headers):
        # Simulate a huge file without actually allocating one: shrink the
        # configured limit for this test instead of generating >10MB of data.
        from app.core.config import get_settings

        get_settings.cache_clear()
        monkeypatch.setenv("MAX_UPLOAD_MB", "0")
        get_settings.cache_clear()

        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (100, 100), "white").save(buf, format="JPEG")

        response = client.post(
            "/api/grade",
            data=valid_form_fields,
            files={"sheet_image": ("sheet.jpg", buf.getvalue(), "image/jpeg")},
        headers=auth_headers,
        )
        assert response.status_code == 413
        get_settings.cache_clear()

    def test_rubric_missing_required_field_returns_422(self, client, valid_form_fields, valid_image_bytes, auth_headers):
        fields = {**valid_form_fields, "rubric_json": json.dumps([{"max_marks": 5}])}
        response = client.post(
            "/api/grade",
            data=fields,
            files={"sheet_image": ("sheet.jpg", valid_image_bytes, "image/jpeg")},
        headers=auth_headers,
        )
        assert response.status_code == 422

    def test_error_responses_never_leak_stack_traces(self, client, valid_form_fields, auth_headers):
        response = client.post(
            "/api/grade",
            data=valid_form_fields,
            files={"sheet_image": ("notes.txt", b"not an image", "text/plain")},
        headers=auth_headers,
        )
        body_text = response.text
        assert "Traceback" not in body_text
        assert "site-packages" not in body_text
