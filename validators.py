from datetime import date, timedelta
from re import fullmatch
from utils import parse_date, get_now


def validate_date_input(date_str: str) -> tuple[bool, str]:
    """Validate date input is reasonable.
    
    Checks:
    - Format is valid (YYYY, YYYY-MM, YYYY-MM-DD)
    - Date is not in the future
    - Date is not too far in the past (max 10 years)
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    cleaned = date_str.strip()
    
    # Validate format first
    if not fullmatch(r"^\d{4}(-\d{2}(-\d{2})?)?$", cleaned):
        return False, "Invalid date format. Use YYYY, YYYY-MM, or YYYY-MM-DD."
    
    # For full dates (YYYY-MM-DD), check reasonableness
    if fullmatch(r"^\d{4}-\d{2}-\d{2}$", cleaned):
        try:
            target_date = parse_date(cleaned)
            today = get_now().date()
            
            if target_date > today:
                return False, "Date cannot be in the future."
            
            if (today - target_date).days > 365 * 10:
                return False, "Date too far in the past (maximum 10 years)."
            
            return True, ""
        except (ValueError, TypeError):
            return False, "Invalid date value."
    
    # For partial dates (YYYY or YYYY-MM), just validate format
    return True, ""


def validate_reminder_window(start_str: str, end_str: str) -> tuple[bool, str]:
    """Validate reminder window hours.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        start_h = int(start_str)
        end_h = int(end_str)
        
        if not (0 <= start_h <= 23):
            return False, "Start hour must be between 0 and 23."
        
        if not (0 <= end_h <= 23):
            return False, "End hour must be between 0 and 23."
        
        return True, ""
    except ValueError:
        return False, "Hours must be valid numbers."


def validate_memory_time(time_str: str) -> tuple[bool, str]:
    """Validate memory time in HH:MM format.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not fullmatch(r"\d{2}:\d{2}$", time_str):
        return False, "Invalid time format. Use HH:MM (e.g., 09:00)."
    
    try:
        h, m = map(int, time_str.split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return False, "Invalid time values."
        return True, ""
    except ValueError:
        return False, "Invalid time format."
