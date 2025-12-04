def roman_to_int(roman):
    values = {'I': 1, 'V': 5, 'X': 10, 'L': 50}
    total = 0
    prev = 0
    for ch in reversed(roman):
        val = values.get(ch, 0)
        total += -val if val < prev else val
        prev = val
    return total
