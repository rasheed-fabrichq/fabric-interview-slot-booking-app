"""
Convert numbers, times and dates into spoken English.

The calling system reads variable values aloud, so it needs words
rather than digits: "twenty" not "20", "one thirty PM" not "13:30".
Digits are read inconsistently by TTS engines ("40" can become
"four zero"), which is why the conversion happens here rather than
being left to the voice agent.
"""

_ONES = [
    'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven',
    'eight', 'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen',
    'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen',
]
_TENS = [
    '', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy',
    'eighty', 'ninety',
]

_ORDINALS = {
    1: 'first', 2: 'second', 3: 'third', 5: 'fifth', 8: 'eighth',
    9: 'ninth', 12: 'twelfth',
}

_MONTHS = [
    '', 'January', 'February', 'March', 'April', 'May', 'June', 'July',
    'August', 'September', 'October', 'November', 'December',
]


def number_to_words(n):
    """Spoken form of a whole number: 40 -> 'forty'.

    Covers 0-999, which is all this application needs (durations and
    day-of-month). Larger values fall back to digits.
    """
    try:
        n = int(n)
    except (TypeError, ValueError):
        return str(n)

    if n < 0 or n > 999:
        return str(n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens] + (f'-{_ONES[ones]}' if ones else '')
    hundreds, rest = divmod(n, 100)
    text = f'{_ONES[hundreds]} hundred'
    return f'{text} {number_to_words(rest)}' if rest else text


def ordinal_to_words(n):
    """Spoken day of month: 1 -> 'first', 21 -> 'twenty-first'."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return str(n)

    if n in _ORDINALS:
        return _ORDINALS[n]
    if n < 20:
        return _ONES[n] + 'th'
    tens, ones = divmod(n, 10)
    if ones == 0:
        # twenty -> twentieth, thirty -> thirtieth
        return _TENS[tens][:-1] + 'ieth'
    return f'{_TENS[tens]}-{_ORDINALS.get(ones, _ONES[ones] + "th")}'


def time_to_words(dt, suffix='today'):
    """Spoken clock time: 13:30 -> 'one thirty PM today'.

    o'clock times drop the minutes entirely ("one PM", not "one zero
    zero PM"), and minutes under ten are spoken as "oh five" so 13:05
    reads "one oh five PM" rather than "one five PM".
    """
    hour = dt.hour
    minute = dt.minute
    meridiem = 'AM' if hour < 12 else 'PM'
    hour12 = hour % 12 or 12

    if minute == 0:
        spoken = f'{number_to_words(hour12)} {meridiem}'
    elif minute < 10:
        spoken = (f'{number_to_words(hour12)} oh {number_to_words(minute)} '
                  f'{meridiem}')
    else:
        spoken = (f'{number_to_words(hour12)} {number_to_words(minute)} '
                  f'{meridiem}')

    return f'{spoken} {suffix}'.strip() if suffix else spoken


def datetime_to_words(dt):
    """Spoken date and time: 'Friday, August first at one PM'."""
    day_name = dt.strftime('%A')
    month_name = _MONTHS[dt.month]
    day = ordinal_to_words(dt.day)
    clock = time_to_words(dt, suffix='')
    return f'{day_name}, {month_name} {day} at {clock}'
