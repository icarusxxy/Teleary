from datetime import date, timedelta
from re import fullmatch
from utils.utils import parse_date, get_now


# Validators return i18n translation keys instead of hardcoded strings.
# Callers resolve the keys via get_text(key, lang) before sending to the user.


def validate_date_input(date_str: str) -> tuple[bool, str]:
    """Validate date input is reasonable.
    
    Checks:
    - Format is valid (YYYY, YYYY-MM, YYYY-MM-DD)
    - Date is not in the future
    - Date is not too far in the past (max 10 years)
    
    Returns:
        Tuple of (is_valid, i18n_error_key)
    """
    cleaned = date_str.strip()
    
    # Validate format first
    if not fullmatch(r"^\d{4}(-\d{2}(-\d{2})?)?$", cleaned):
        return False, "validator_date_format"
    
    # For full dates (YYYY-MM-DD), check reasonableness
    if fullmatch(r"^\d{4}-\d{2}-\d{2}$", cleaned):
        try:
            target_date = parse_date(cleaned)
            today = get_now().date()
            
            if target_date > today:
                return False, "validator_date_future"
            
            if (today - target_date).days > 365 * 10:
                return False, "validator_date_too_old"
            
            return True, ""
        except (ValueError, TypeError):
            return False, "validator_date_invalid"
    
    # For partial dates (YYYY or YYYY-MM), just validate format
    return True, ""


def validate_reminder_window(start_str: str, end_str: str) -> tuple[bool, str]:
    """Validate reminder window hours.
    
    Returns:
        Tuple of (is_valid, i18n_error_key)
    """
    try:
        start_h = int(start_str)
        end_h = int(end_str)
        
        if not (0 <= start_h <= 23):
            return False, "validator_start_hours_range"
        
        if not (0 <= end_h <= 23):
            return False, "validator_end_hours_range"
        
        return True, ""
    except ValueError:
        return False, "validator_hours_not_numbers"


def validate_memory_time(time_str: str) -> tuple[bool, str]:
    """Validate memory time in HH:MM format.
    
    Returns:
        Tuple of (is_valid, i18n_error_key)
    """
    if not fullmatch(r"\d{2}:\d{2}$", time_str):
        return False, "validator_time_format"
    
    try:
        h, m = map(int, time_str.split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return False, "validator_time_values"
        return True, ""
    except ValueError:
        return False, "validator_time_format"
