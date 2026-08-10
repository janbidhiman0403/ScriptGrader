class TestPersistence:
    def _grade(self, client, auth_headers, valid_form_fields, valid_image_bytes, question_number="1"):
        fields = {**valid_form_fields, "question_number": question_number}
        return client.post(
            "/api/grade",
            data=fields,
            files={"sheet_image": ("sheet.jpg", valid_image_bytes, "image/jpeg")},
            headers=auth_headers,
        )

    def test_grading_persists_an_evaluation(self, client, auth_headers, valid_form_fields, valid_image_bytes):
        self._grade(client, auth_headers, valid_form_fields, valid_image_bytes)
        response = client.get("/api/evaluations", headers=auth_headers)
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_list_requires_auth(self, client):
        response = client.get("/api/evaluations")
        assert response.status_code == 401

    def test_list_returns_most_recent_first(self, client, auth_headers, valid_form_fields, valid_image_bytes):
        self._grade(client, auth_headers, valid_form_fields, valid_image_bytes, question_number="1")
        self._grade(client, auth_headers, valid_form_fields, valid_image_bytes, question_number="2")
        response = client.get("/api/evaluations", headers=auth_headers)
        body = response.json()
        assert body[0]["question_number"] == "2"
        assert body[1]["question_number"] == "1"

    def test_get_single_evaluation(self, client, auth_headers, valid_form_fields, valid_image_bytes):
        self._grade(client, auth_headers, valid_form_fields, valid_image_bytes)
        eval_id = client.get("/api/evaluations", headers=auth_headers).json()[0]["id"]
        response = client.get(f"/api/evaluations/{eval_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["id"] == eval_id

    def test_get_nonexistent_evaluation_returns_404(self, client, auth_headers):
        response = client.get("/api/evaluations/does-not-exist", headers=auth_headers)
        assert response.status_code == 404

    def test_new_evaluation_starts_unreviewed(self, client, auth_headers, valid_form_fields, valid_image_bytes):
        self._grade(client, auth_headers, valid_form_fields, valid_image_bytes)
        record = client.get("/api/evaluations", headers=auth_headers).json()[0]
        assert record["reviewed"] is False
        assert record["review_note"] is None


class TestOverride:
    def _grade_and_get_id(self, client, auth_headers, valid_form_fields, valid_image_bytes):
        client.post(
            "/api/grade",
            data=valid_form_fields,
            files={"sheet_image": ("sheet.jpg", valid_image_bytes, "image/jpeg")},
            headers=auth_headers,
        )
        return client.get("/api/evaluations", headers=auth_headers).json()[0]["id"]

    def test_override_updates_awarded_marks(self, client, auth_headers, valid_form_fields, valid_image_bytes):
        eval_id = self._grade_and_get_id(client, auth_headers, valid_form_fields, valid_image_bytes)
        response = client.patch(
            f"/api/evaluations/{eval_id}",
            json={"criteria": [{"name": "Concept accuracy", "awarded": 5}]},
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        updated = next(c for c in body["criteria"] if c["name"] == "Concept accuracy")
        assert updated["awarded"] == 5

    def test_override_recomputes_total_server_side(self, client, auth_headers, valid_form_fields, valid_image_bytes):
        eval_id = self._grade_and_get_id(client, auth_headers, valid_form_fields, valid_image_bytes)
        response = client.patch(
            f"/api/evaluations/{eval_id}",
            json={"criteria": [{"name": "Concept accuracy", "awarded": 5}, {"name": "Completeness", "awarded": 5}]},
            headers=auth_headers,
        )
        body = response.json()
        computed = sum(c["awarded"] for c in body["criteria"])
        assert body["total_awarded"] == computed == 10

    def test_override_marks_as_reviewed(self, client, auth_headers, valid_form_fields, valid_image_bytes):
        eval_id = self._grade_and_get_id(client, auth_headers, valid_form_fields, valid_image_bytes)
        response = client.patch(
            f"/api/evaluations/{eval_id}",
            json={"criteria": [{"name": "Concept accuracy", "awarded": 5}], "review_note": "Verified by hand"},
            headers=auth_headers,
        )
        body = response.json()
        assert body["reviewed"] is True
        assert body["review_note"] == "Verified by hand"

    def test_override_preserves_original_criteria(self, client, auth_headers, valid_form_fields, valid_image_bytes):
        eval_id = self._grade_and_get_id(client, auth_headers, valid_form_fields, valid_image_bytes)
        client.patch(
            f"/api/evaluations/{eval_id}",
            json={"criteria": [{"name": "Concept accuracy", "awarded": 5}]},
            headers=auth_headers,
        )
        record = client.get(f"/api/evaluations/{eval_id}", headers=auth_headers).json()
        original = next(c for c in record["criteria_original"] if c["name"] == "Concept accuracy")
        assert original["awarded"] == 4  # the mock's original value, untouched

    def test_override_unknown_criterion_returns_400(self, client, auth_headers, valid_form_fields, valid_image_bytes):
        eval_id = self._grade_and_get_id(client, auth_headers, valid_form_fields, valid_image_bytes)
        response = client.patch(
            f"/api/evaluations/{eval_id}",
            json={"criteria": [{"name": "Nonexistent criterion", "awarded": 5}]},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_override_exceeding_max_marks_returns_400(self, client, auth_headers, valid_form_fields, valid_image_bytes):
        eval_id = self._grade_and_get_id(client, auth_headers, valid_form_fields, valid_image_bytes)
        response = client.patch(
            f"/api/evaluations/{eval_id}",
            json={"criteria": [{"name": "Concept accuracy", "awarded": 999}]},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_override_requires_auth(self, client, auth_headers, valid_form_fields, valid_image_bytes):
        eval_id = self._grade_and_get_id(client, auth_headers, valid_form_fields, valid_image_bytes)
        response = client.patch(
            f"/api/evaluations/{eval_id}",
            json={"criteria": [{"name": "Concept accuracy", "awarded": 5}]},
        )
        assert response.status_code == 401

    def test_override_nonexistent_evaluation_returns_404(self, client, auth_headers):
        response = client.patch(
            "/api/evaluations/does-not-exist",
            json={"criteria": [{"name": "X", "awarded": 1}]},
            headers=auth_headers,
        )
        assert response.status_code == 404
