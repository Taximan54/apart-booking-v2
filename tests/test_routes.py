"""
Проверка карты адресов API: у каждого важного адреса должен быть именно тот
обработчик, который нужен. Именно такая ошибка (декоратор POST /api/bookings
стоял над не той функцией) ломала бронирование с сайта.
"""
import pytest

EXPECTED = {
    ("GET", "/health"): "health",
    ("POST", "/api/bookings"): "create_booking",
    ("GET", "/api/bookings"): "get_bookings",
    ("POST", "/api/bookings/{booking_ref}/confirm"): "confirm_booking",
    ("POST", "/api/bookings/{booking_ref}/cancel"): "cancel_booking_api",
    ("DELETE", "/api/bookings/{booking_ref}"): "delete_booking_api",
    ("POST", "/api/payment-notify"): "payment_notify",
    ("POST", "/api/admin/manual-booking"): "create_manual_booking",
    ("POST", "/api/admin/login"): "admin_login",
    ("GET", "/api/prices"): "get_prices",
    ("POST", "/api/prices"): "set_prices",
    ("GET", "/api/booked-dates"): "booked_dates",
    ("GET", "/api/photos"): "list_photos",
    ("POST", "/api/photos/upload"): "upload_photo",
    ("POST", "/api/upload-passport-photo"): "upload_passport_photo",
    ("GET", "/api/admin/passport-photo/{booking_ref}/{slot}"): "get_passport_photo",
    ("GET", "/api/admin/contract-pdf/{booking_ref}/{doc_type}"): "get_signed_contract_pdf",
    ("POST", "/api/admin/contract-preview"): "contract_preview",
    ("GET", "/api/contracts"): "list_contracts",
    ("GET", "/api/sign/{token}"): "get_sign_info",
    ("POST", "/api/sign/{token}/confirm"): "confirm_sign",
    ("GET", "/api/complete/{token}"): "get_complete_info",
    ("POST", "/api/complete/{token}/submit"): "submit_complete",
    ("GET", "/api/discounts"): "get_discounts",
    ("GET", "/api/places"): "get_places",
    ("GET", "/api/site-settings"): "get_site_settings",
}


@pytest.fixture(scope="module")
def routes():
    """
    Карта «метод + адрес -> имя обработчика», собранная из описания API (OpenAPI):
    это работает и в старых, и в новых версиях FastAPI. Имя обработчика —
    начало идентификатора операции (например, create_booking_api_bookings_post).
    """
    import main
    spec = main.app.openapi()
    table = {}
    for path, item in spec["paths"].items():
        for method, op in item.items():
            table[(method.upper(), path)] = op.get("operationId", "")
    return table


@pytest.mark.parametrize("key,handler", sorted(EXPECTED.items()))
def test_important_route_has_right_handler(routes, key, handler):
    assert key in routes, f"нет адреса {key}"
    got = routes[key]
    assert got.startswith(handler + "_"), f"{key}: обработчик {got!r}, ожидался {handler}"


def test_no_route_is_bound_to_private_helper(routes):
    """Обработчик адреса не может быть служебной функцией с именем на «_»."""
    bad = {k: v for k, v in routes.items() if v.startswith("_")}
    assert not bad, f"адреса привязаны к служебным функциям: {bad}"


def test_route_count_not_dropped(routes):
    assert len(routes) >= 80, f"адресов стало {len(routes)}, раньше было 83"
