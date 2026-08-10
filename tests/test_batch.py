import io

from PIL import Image


def _image_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (300, 200), "white").save(buf, format="JPEG")
    return buf.getvalue()


class TestBatchGrading:
    def test_batch_grades_multiple_images(self, client, auth_headers, valid_form_fields):
        files = [
            ("sheet_images", ("a.jpg", _image_bytes(), "image/jpeg")),
            ("sheet_images", ("b.jpg", _image_bytes(), "image/jpeg")),
        ]
        response = client.post(
            "/api/grade/batch", data=valid_form_fields, files=files, headers=auth_headers
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert all(item["result"] is not None for item in body)
        assert all(item["error"] is None for item in body)

    def test_batch_reports_partial_failure_without_failing_whole_batch(
        self, client, auth_headers, valid_form_fields
    ):
        files = [
            ("sheet_images", ("good.jpg", _image_bytes(), "image/jpeg")),
            ("sheet_images", ("bad.txt", b"not an image", "text/plain")),
        ]
        response = client.post(
            "/api/grade/batch", data=valid_form_fields, files=files, headers=auth_headers
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert body[0]["result"] is not None
        assert body[0]["error"] is None
        assert body[1]["result"] is None
        assert body[1]["error"] is not None

    def test_batch_requires_auth(self, client, valid_form_fields):
        files = [("sheet_images", ("a.jpg", _image_bytes(), "image/jpeg"))]
        response = client.post("/api/grade/batch", data=valid_form_fields, files=files)
        assert response.status_code == 401

    def test_batch_persists_successful_items(self, client, auth_headers, valid_form_fields):
        files = [
            ("sheet_images", ("a.jpg", _image_bytes(), "image/jpeg")),
            ("sheet_images", ("b.jpg", _image_bytes(), "image/jpeg")),
        ]
        client.post("/api/grade/batch", data=valid_form_fields, files=files, headers=auth_headers)
        evaluations = client.get("/api/evaluations", headers=auth_headers).json()
        assert len(evaluations) == 2

    def test_batch_items_share_a_batch_id(self, client, auth_headers, valid_form_fields):
        files = [
            ("sheet_images", ("a.jpg", _image_bytes(), "image/jpeg")),
            ("sheet_images", ("b.jpg", _image_bytes(), "image/jpeg")),
        ]
        client.post("/api/grade/batch", data=valid_form_fields, files=files, headers=auth_headers)
        evaluations = client.get("/api/evaluations", headers=auth_headers).json()
        batch_ids = {e["batch_id"] for e in evaluations}
        assert len(batch_ids) == 1
        assert None not in batch_ids

    def test_batch_filter_by_batch_id(self, client, auth_headers, valid_form_fields):
        files = [("sheet_images", ("a.jpg", _image_bytes(), "image/jpeg"))]
        client.post("/api/grade/batch", data=valid_form_fields, files=files, headers=auth_headers)
        batch_id = client.get("/api/evaluations", headers=auth_headers).json()[0]["batch_id"]

        response = client.get(f"/api/evaluations?batch_id={batch_id}", headers=auth_headers)
        assert len(response.json()) == 1
