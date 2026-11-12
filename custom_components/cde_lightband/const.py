"""Constants for the CDE Lightband integration."""

from homeassistant.const import (
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)

DOMAIN = "cde_lightband"

RATES_URL = "https://cdelightband.com/residential/energy/rates-fees/"
INTERNET_URL = "https://cdelightband.com/residential/internet/"

CONF_HISTORY_DAYS = "history_days"

DEFAULT_SCAN_INTERVAL = 60  # minutes
DEFAULT_HISTORY_DAYS = 30   # days

CONF_INTERNET_PLAN = "internet_plan"
DEFAULT_INTERNET_PLAN = "none"
INTERNET_PLAN_OPTIONS = {
    "none": "None",
    "300": "300 Mbps",
    "600": "600 Mbps",
    "1000": "1 Gig",
    "2500": "2.5 Gig",
}

ATTR_ACCOUNT_NUMBER = "account_number"
ATTR_SERVICE_ADDRESS = "service_address"
ATTR_DUE_DATE = "due_date"
ATTR_IS_PAST_DUE = "is_past_due"
ATTR_PAST_DUE_AMOUNT = "past_due_amount"
ATTR_LAST_PAYMENT_DATE = "last_payment_date"
ATTR_LAST_BILL_DATE = "last_bill_date"
ATTR_METER_ID = "meter_id"
ATTR_READING_DATE = "reading_date"
ATTR_MONTH_TO_DATE_KWH = "month_to_date_kwh"
ATTR_DAILY_KWH = "daily_kwh"
ATTR_ENERGY_RATE = "energy_rate"
ATTR_CUSTOMER_CHARGE = "customer_charge"
ATTR_GRID_ACCESS_CHARGE = "grid_access_charge"
ATTR_INTERNET_PLAN = "internet_plan"
ATTR_INTERNET_PRICE = "internet_price"
ATTR_RATE_MONTH = "rate_month"
ATTR_RATES_FETCHED = "rates_fetched"
