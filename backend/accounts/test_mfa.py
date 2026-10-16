import base64
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.db import close_old_connections, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django_otp.oath import TOTP

from auditlog.models import AuditEvent

from . import mfa
from .models import AccountMFA

KEY = Fernet.generate_key().decode()
PASSWORD = "SyntheticMfaPassword2026!"
User = get_user_model()


@override_settings(MFA_ENCRYPTION_KEYS=[KEY])
class MFATests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="mfa@example.com", password=PASSWORD, is_staff=True, is_superuser=True
        )
        self.client.force_login(self.user)

    def post(self, path, data, client=None):
        return (client or self.client).post(
            "/api/auth/" + path, json.dumps(data), content_type="application/json"
        )

    def code(self, *, offset=0):
        device = AccountMFA.objects.get(user=self.user)
        otp = TOTP(mfa.secret_bytes(device))
        otp.time = time.time() + offset * 30
        return f"{otp.token():06d}"

    def enroll(self):
        result = self.post("mfa/", {"current_password": PASSWORD})
        self.assertEqual(result.status_code, 200)
        result = self.post(
            "mfa/manage/", {"action": "confirm", "current_password": PASSWORD, "code": self.code()}
        )
        self.assertEqual(result.status_code, 200, result.content)
        return result.json()["recovery_codes"]

    def challenge(self, client):
        result = self.post("login/", {"email": self.user.email, "password": PASSWORD}, client)
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json()["mfa_required"])
        self.assertNotIn("user", result.json())
        self.assertEqual(client.get("/api/auth/me/").status_code, 401)

    def test_enrollment_encrypts_seed_and_hashes_recovery_invalidates_other_sessions(self):
        other = Client()
        other.force_login(self.user)
        setup = self.post("mfa/", {"current_password": PASSWORD}).json()
        device = AccountMFA.objects.get(user=self.user)
        self.assertNotIn(setup["secret"], device.encrypted_secret)
        self.assertEqual(base64.b32decode(setup["secret"]), mfa.secret_bytes(device))
        self.assertIn("otpauth://totp/", setup["uri"])
        self.assertFalse(self.client.get("/api/auth/mfa/").json()["enabled"])
        response = self.post(
            "mfa/manage/", {"action": "confirm", "current_password": PASSWORD, "code": self.code()}
        )
        codes = response.json()["recovery_codes"]
        device.refresh_from_db()
        self.assertEqual(len(codes), 8)
        self.assertNotIn(codes[0], json.dumps(device.recovery_hashes))
        self.assertEqual(other.get("/api/auth/me/").status_code, 401)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)
        events = json.dumps(list(AuditEvent.objects.values("metadata", "changes")), default=str)
        self.assertNotIn(setup["secret"], events)
        for code in codes:
            self.assertNotIn(code, events)

    def test_password_alone_and_replayed_totp_never_authenticate(self):
        self.enroll()
        second = Client()
        self.challenge(second)
        self.assertEqual(self.post("mfa/login/", {"code": self.code()}, second).status_code, 401)
        with patch("django_otp.oath.time", return_value=time.time() + 30):
            code = self.code(offset=1)
            self.assertEqual(self.post("mfa/login/", {"code": code}, second).status_code, 200)
            self.assertEqual(second.get("/api/auth/me/").status_code, 200)
            third = Client()
            self.challenge(third)
            self.assertEqual(self.post("mfa/login/", {"code": code}, third).status_code, 401)

    def test_starting_a_challenge_removes_the_previous_request_identity(self):
        self.enroll()
        response = self.post("login/", {"email": self.user.email, "password": PASSWORD})
        self.assertTrue(response.json()["mfa_required"])
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_recovery_is_single_use_and_never_disables_mfa(self):
        codes = self.enroll()
        second = Client()
        self.challenge(second)
        self.assertEqual(self.post("mfa/login/", {"code": codes[0]}, second).status_code, 200)
        self.assertEqual(second.get("/api/auth/mfa/").json()["recovery_codes_remaining"], 7)
        third = Client()
        self.challenge(third)
        self.assertEqual(self.post("mfa/login/", {"code": codes[0]}, third).status_code, 401)
        self.assertTrue(AccountMFA.objects.get(user=self.user).confirmed_at)

    def test_expired_challenge_password_change_and_deactivation_are_rejected(self):
        codes = self.enroll()
        second = Client()
        self.challenge(second)
        session = second.session
        session[mfa.CHALLENGE]["created"] -= 301
        session.save()
        self.assertEqual(self.post("mfa/login/", {"code": codes[0]}, second).status_code, 401)
        self.challenge(second)
        self.user.set_password("DifferentSyntheticPassword2026!")
        self.user.save(update_fields=["password"])
        self.assertEqual(self.post("mfa/login/", {"code": codes[0]}, second).status_code, 401)
        self.user.set_password(PASSWORD)
        self.user.save(update_fields=["password"])
        self.challenge(second)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(self.post("mfa/login/", {"code": codes[0]}, second).status_code, 401)

    def test_admin_cannot_bypass_mfa_and_accepts_one_use_recovery(self):
        codes = self.enroll()
        second = Client()
        result = second.post(
            "/admin/login/", {"username": self.user.email, "password": PASSWORD, "next": "/admin/"}
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(second.get("/api/auth/me/").status_code, 401)
        result = second.post(
            "/admin/login/",
            {
                "username": self.user.email,
                "password": PASSWORD,
                "otp_code": codes[0],
                "next": "/admin/",
            },
        )
        self.assertEqual(result.status_code, 302)
        self.assertEqual(second.get("/admin/").status_code, 200)
        bypass = Client()
        self.user.refresh_from_db()
        bypass.force_login(self.user)
        self.assertEqual(bypass.get("/api/auth/me/").status_code, 401)
        self.assertEqual(bypass.get("/admin/").status_code, 302)

    def test_admin_missing_credentials_returns_form_errors_without_500(self):
        self.enroll()
        anonymous = Client()
        for data in [{}, {"username": self.user.email}, {"password": PASSWORD}]:
            with self.subTest(fields=list(data)):
                response = anonymous.post("/admin/login/", data)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(anonymous.get("/api/auth/me/").status_code, 401)

    def test_manage_requires_current_password_and_factor_and_rotates_recovery(self):
        codes = self.enroll()
        self.assertEqual(self.post("mfa/", {"current_password": PASSWORD}).status_code, 400)
        for password, code in [("wrong", codes[0]), (PASSWORD, "wrong")]:
            self.assertEqual(
                self.post(
                    "mfa/manage/", {"action": "disable", "current_password": password, "code": code}
                ).status_code,
                400,
            )
        response = self.post(
            "mfa/manage/", {"action": "recovery", "current_password": PASSWORD, "code": codes[0]}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.post(
                "mfa/manage/", {"action": "disable", "current_password": PASSWORD, "code": codes[1]}
            ).status_code,
            400,
        )
        newcodes = response.json()["recovery_codes"]
        self.assertEqual(
            self.post(
                "mfa/manage/",
                {"action": "disable", "current_password": PASSWORD, "code": newcodes[0]},
            ).status_code,
            200,
        )
        self.assertFalse(AccountMFA.objects.filter(user=self.user).exists())
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)

    def test_setup_expiry_unknown_fields_missing_configuration_and_csrf(self):
        self.assertEqual(Client().get("/api/auth/mfa/").status_code, 401)
        self.assertEqual(
            self.post("mfa/", {"current_password": PASSWORD, "user": 100}).status_code, 400
        )
        with override_settings(MFA_ENCRYPTION_KEYS=[]):
            self.assertEqual(self.post("mfa/", {"current_password": PASSWORD}).status_code, 503)
        self.post("mfa/", {"current_password": PASSWORD})
        AccountMFA.objects.filter(user=self.user).update(
            setup_expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(
            self.post(
                "mfa/manage/",
                {"action": "confirm", "current_password": PASSWORD, "code": self.code()},
            ).status_code,
            400,
        )
        self.assertEqual(
            Client(enforce_csrf_checks=True)
            .post(
                "/api/auth/mfa/login/",
                json.dumps({"code": "123456"}),
                content_type="application/json",
            )
            .status_code,
            403,
        )

    def test_encryption_key_rotation_and_bad_key_fail_closed(self):
        codes = self.enroll()
        olddevice = AccountMFA.objects.get(user=self.user)
        secret = mfa.secret_bytes(olddevice)
        with override_settings(MFA_ENCRYPTION_KEYS=[Fernet.generate_key().decode(), KEY]):
            self.assertEqual(mfa.secret_bytes(olddevice), secret)
        with override_settings(MFA_ENCRYPTION_KEYS=[Fernet.generate_key().decode()]):
            from cryptography.fernet import InvalidToken

            self.assertRaises(InvalidToken, mfa.secret_bytes, olddevice)
        self.assertEqual(len(codes), 8)

    def test_password_reset_changes_password_but_preserves_factor(self):
        codes = self.enroll()
        self.user.refresh_from_db()
        token = default_token_generator.make_token(self.user)
        newpassword = "ResetSyntheticPassword2026!"
        response = self.post(
            "password-reset/confirm/",
            {
                "uid": urlsafe_base64_encode(force_bytes(self.user.pk)),
                "token": token,
                "password": newpassword,
                "password_confirm": newpassword,
            },
            Client(),
        )
        self.assertEqual(response.status_code, 200)
        other = Client()
        response = self.post("login/", {"email": self.user.email, "password": newpassword}, other)
        self.assertTrue(response.json()["mfa_required"])
        self.assertEqual(other.get("/api/auth/me/").status_code, 401)
        self.assertEqual(self.post("mfa/login/", {"code": codes[0]}, other).status_code, 200)

    def test_account_and_ip_throttle_limit_guesses_across_challenges(self):
        self.enroll()
        second = Client()
        self.challenge(second)
        for _ in range(10):
            self.assertEqual(self.post("mfa/login/", {"code": "invalid"}, second).status_code, 401)
        self.assertEqual(self.post("mfa/login/", {"code": "invalid"}, second).status_code, 429)


@override_settings(MFA_ENCRYPTION_KEYS=[KEY])
class MFAConcurrencyTests(TransactionTestCase):
    def test_same_recovery_code_is_consumed_once_under_concurrency(self):
        user = User.objects.create_user(email="concurrent-mfa@example.com", password=PASSWORD)
        with transaction.atomic():
            device, _, _ = mfa.setup(user)
            device.confirmed_at = timezone.now()
            device.save(update_fields=["confirmed_at"])
            code = mfa.recovery_codes(device)[0]

        def attempt(_):
            close_old_connections()
            try:
                with transaction.atomic():
                    current = mfa.lock_user(user.pk)
                    device = mfa.lock_device(current)
                    return mfa.verify(device, code)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(attempt, range(2))), [False, True])

    def test_same_totp_is_consumed_once_under_concurrency(self):
        user = User.objects.create_user(email="totp-race@example.com", password=PASSWORD)
        with transaction.atomic():
            device, _, _ = mfa.setup(user)
            device.confirmed_at = timezone.now()
            device.save(update_fields=["confirmed_at"])
            otp = TOTP(mfa.secret_bytes(device))
            code = f"{otp.token():06d}"

        def attempt(_):
            close_old_connections()
            try:
                with transaction.atomic():
                    current = mfa.lock_user(user.pk)
                    return mfa.verify(mfa.lock_device(current), code)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(attempt, range(2))), [False, True])
