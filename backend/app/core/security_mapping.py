# OWASP Top 10 2025
OWASP_2025 = {
    "A01": "Broken Access Control",
    "A02": "Security Misconfiguration",
    "A03": "Software Supply Chain Failures",
    "A04": "Cryptographic Failures",
    "A05": "Injection",
    "A06": "Insecure Design",
    "A07": "Authentication Failures",
    "A08": "Software or Data Integrity Failures",
    "A09": "Security Logging and Alerting Failures",
    "A10": "Mishandling of Exceptional Conditions",
}


# =========================================================
# CWE → OWASP mapping
# =========================================================

CWE_TO_OWASP = {

    # ---------------------------
    # A01 Broken Access Control
    # ---------------------------
    "CWE-284": "A01",  # Improper Access Control
    "CWE-285": "A01",
    "CWE-639": "A01",
    "CWE-732": "A01",  # Incorrect permission assignment


    # ---------------------------
    # A02 Security Misconfiguration
    # ---------------------------
    "CWE-16": "A02",
    "CWE-295": "A02",   # SSL verification disabled
    "CWE-377": "A02",   # insecure temp file
    "CWE-933": "A02",


    # ---------------------------
    # A03 Supply Chain
    # ---------------------------
    "CWE-1104": "A03",
    "CWE-1357": "A03",


    # ---------------------------
    # A04 Cryptographic Failures
    # ---------------------------
    "CWE-326": "A04",
    "CWE-327": "A04",
    "CWE-328": "A04",


    # ---------------------------
    # A05 Injection
    # ---------------------------
    "CWE-77": "A05",   # command injection
    "CWE-78": "A05",
    "CWE-79": "A05",
    "CWE-89": "A05",
    "CWE-94": "A05",   # code injection
    "CWE-611": "A05",  # XXE
    "CWE-918": "A05",  # SSRF


    # ---------------------------
    # A06 Insecure Design
    # ---------------------------
    "CWE-20": "A06",
    "CWE-22": "A06",   # path traversal
    "CWE-840": "A06",
    "B403": "CWE-502",


    # ---------------------------
    # A07 Authentication Failures
    # ---------------------------
    "CWE-287": "A07",
    "CWE-522": "A07",
    "CWE-798": "A07",


    # ---------------------------
    # A08 Software/Data Integrity
    # ---------------------------
    "CWE-353": "A08",
    "CWE-494": "A08",
    "CWE-502": "A08",


    # ---------------------------
    # A09 Logging Failures
    # ---------------------------
    "CWE-778": "A09",


    # ---------------------------
    # A10 Error / Resource Handling
    # ---------------------------
    "CWE-703": "A10",  # improper exception handling
    "CWE-400": "A10",  # resource exhaustion
    "CWE-330": "A10",  # weak randomness
}