import pycountry
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from config.geography import ARGENTINE_PROVINCE_CODES


class ReferenceTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="reference@example.com")
        self.client.force_authenticate(self.user)

    def test_requires_session(self):
        self.client.force_authenticate(None)
        for url in ["/api/reference/countries/", "/api/reference/countries/AR/subdivisions/"]:
            self.assertEqual(self.client.get(url).status_code, 401)

    def test_unique_countries_with_argentina(self):
        response = self.client.get("/api/reference/countries/")
        self.assertEqual(response.status_code, 200)
        rows = response.data["results"]
        codes = [row["code"] for row in rows]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(set(codes), {country.alpha_2 for country in pycountry.countries})
        self.assertTrue(all(row["name"] for row in rows))
        self.assertIn("AR", codes)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_argentina_has_24_canonical_subdivisions(self):
        response = self.client.get("/api/reference/countries/ar/subdivisions/")
        self.assertEqual(response.status_code, 200)
        rows = response.data["results"]
        self.assertEqual({row["code"]: row["name"] for row in rows}, ARGENTINE_PROVINCE_CODES)
        self.assertEqual(len(rows), 24)

    def test_us_includes_california(self):
        rows = self.client.get("/api/reference/countries/US/subdivisions/").data["results"]
        self.assertIn({"code": "US-CA", "name": "California"}, rows)

    def test_valid_country_without_subdivisions(self):
        country = next(
            c for c in pycountry.countries if not pycountry.subdivisions.get(country_code=c.alpha_2)
        )
        response = self.client.get(f"/api/reference/countries/{country.alpha_2}/subdivisions/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"results": []})

    def test_invalid_country_is_404(self):
        for country in ["ZZ", "ARG", "123"]:
            self.assertEqual(
                self.client.get(f"/api/reference/countries/{country}/subdivisions/").status_code,
                404,
            )

    def test_read_only(self):
        self.assertEqual(self.client.post("/api/reference/countries/", {}).status_code, 405)
