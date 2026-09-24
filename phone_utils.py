"""
Phone number normalisation and validation for candidate uploads.

Numbers arrive from spreadsheets in whatever shape the source system or
a human left them in. Observed variants for Indian mobiles:

    9876543210          bare 10-digit
    09876543210         leading trunk zero
    919876543210        country code, no plus
    +91 98765 43210     spaces
    +91-9876-543210     hyphens
    00919876543210      international prefix as 00
    919876543210.0      Excel read the column as a float
    '+919876543210      leading apostrophe from Excel text coercion

All are normalised to E.164 (+919876543210). Anything that cannot be
resolved confidently is rejected with a reason rather than guessed at,
because a wrong number means calling a stranger.
"""
import re

# Default country for bare national numbers. India: +91, mobiles are
# 10 digits starting 6-9.
DEFAULT_COUNTRY_CODE = '91'
INDIA_MOBILE_LENGTH = 10
INDIA_MOBILE_FIRST_DIGIT = '6789'

# Bounds from ITU-T E.164: a full international number is at most 15
# digits, and nothing real is shorter than 8.
E164_MAX_DIGITS = 15
E164_MIN_DIGITS = 8


def _strip_to_digits(raw):
    """Reduce free-form input to a leading-plus flag and its digits."""
    text = str(raw).strip()

    # Excel writes text-formatted numbers with a leading apostrophe, and
    # turns a numeric column into a float ("919876543210.0").
    text = text.lstrip("'")
    if re.fullmatch(r'\d+\.0+', text):
        text = text.split('.')[0]

    has_plus = text.startswith('+')
    digits = re.sub(r'\D', '', text)
    return has_plus, digits


def _strip_repeated_country_code(digits, country_code):
    """Collapse a country code that appears more than once.

    Source systems that prefix "+91-" to a column of numbers that
    already carry it produce "+91-+91 75699 44695", which reduces to
    919175699446950 -- 12 digits after the first 91.

    Only strips while the remainder still resolves to a valid national
    mobile number, so a genuine number is never truncated. A leading
    trunk zero between the codes ("+91-09876543210") is handled too.
    """
    national_len = INDIA_MOBILE_LENGTH
    # Only the default country's format is known well enough to verify
    # what is left, so leave other country codes untouched.
    if country_code != DEFAULT_COUNTRY_CODE:
        return digits

    while (digits.startswith(country_code)
           and len(digits) > len(country_code) + national_len):
        remainder = digits[len(country_code):].lstrip('0')
        # Stop unless dropping this copy leaves something that still
        # starts with the country code or is itself a valid mobile.
        if remainder.startswith(country_code):
            digits = remainder
            continue
        if (len(remainder) == national_len
                and remainder[0] in INDIA_MOBILE_FIRST_DIGIT):
            digits = country_code + remainder
        break

    return digits


def normalize_phone(raw, default_country_code=DEFAULT_COUNTRY_CODE):
    """Normalise a phone number to E.164.

    Returns (normalized, error). Exactly one is None. `normalized`
    looks like '+919876543210'.
    """
    if raw is None:
        return None, 'Phone number is required'

    text = str(raw).strip()
    if not text or text.lower() in ('nan', 'none', 'null', '-'):
        return None, 'Phone number is required'

    has_plus, digits = _strip_to_digits(raw)

    if not digits:
        return None, f'No digits found in phone number: {text!r}'

    digits = _strip_repeated_country_code(digits, default_country_code)

    # 00 is the international access prefix in India and much of the
    # world -- 0091... means +91...
    if digits.startswith('00'):
        digits = digits[2:]
        has_plus = True

    if has_plus:
        # Already international; trust the country code as given.
        normalized_digits = digits
    elif len(digits) == INDIA_MOBILE_LENGTH:
        # Bare national number.
        normalized_digits = default_country_code + digits
    elif (digits.startswith('0')
            and len(digits) == INDIA_MOBILE_LENGTH + 1):
        # Trunk prefix: 09876543210 -> +919876543210
        normalized_digits = default_country_code + digits[1:]
    elif digits.startswith(default_country_code) and len(digits) == len(
            default_country_code) + INDIA_MOBILE_LENGTH:
        # Country code present without a plus.
        normalized_digits = digits
    else:
        # Ambiguous: could be a foreign number missing its plus, a typo,
        # or a landline. Guessing here risks dialling a stranger.
        return None, (
            f'Cannot determine country code for {text!r} '
            f'({len(digits)} digits). Prefix it with + and the country '
            f'code, e.g. +{default_country_code}XXXXXXXXXX')

    if len(normalized_digits) > E164_MAX_DIGITS:
        return None, (
            f'Phone number {text!r} has {len(normalized_digits)} digits; '
            f'the maximum is {E164_MAX_DIGITS}')
    if len(normalized_digits) < E164_MIN_DIGITS:
        return None, (
            f'Phone number {text!r} has only {len(normalized_digits)} '
            f'digits')

    # For the default country we know the mobile format, so we can
    # catch landlines and typo'd numbers that would silently fail to
    # connect at call time.
    if normalized_digits.startswith(default_country_code):
        national = normalized_digits[len(default_country_code):]
        if len(national) != INDIA_MOBILE_LENGTH:
            return None, (
                f'{text!r} is not a valid {INDIA_MOBILE_LENGTH}-digit '
                f'mobile number (got {len(national)} digits after +'
                f'{default_country_code})')
        if national[0] not in INDIA_MOBILE_FIRST_DIGIT:
            return None, (
                f'{text!r} is not a mobile number -- Indian mobiles '
                f'start with {"/".join(INDIA_MOBILE_FIRST_DIGIT)}')

    return '+' + normalized_digits, None


def is_valid_phone(raw, default_country_code=DEFAULT_COUNTRY_CODE):
    """True if the number normalises cleanly."""
    normalized, _ = normalize_phone(raw, default_country_code)
    return normalized is not None


def mask_phone(normalized):
    """Partially mask a number for logs, so full numbers are not
    written to disk in plain text."""
    if not normalized:
        return ''
    text = str(normalized)
    if len(text) <= 4:
        return text
    return text[:-7] + '*****' + text[-2:] if len(text) > 9 else '*' * (
        len(text) - 2) + text[-2:]
