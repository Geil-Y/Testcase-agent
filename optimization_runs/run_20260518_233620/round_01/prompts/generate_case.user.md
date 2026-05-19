Write a test case for the following requirement.

Requirement ID: {{ requirement_key }}
Requirement description: {{ description }}
{% if supplementary_info %}Supplementary information: {{ supplementary_info }}{% endif %}

Coverage dimension: {{ coverage_dimension }}
Case intent: {{ case_intent }}

{% if extracted_signals %}Known BMS signals (use these exact names in expected results): {{ extracted_signals }}{% endif %}
{% if extracted_thresholds %}Known thresholds (reference these directly): {{ extracted_thresholds }}{% endif %}
{% if extracted_timing %}Known timing parameters (reference these directly): {{ extracted_timing }}{% endif %}
{% if missing_info %}Critical missing information — you MUST use [NEEDS REVIEW] placeholders in expected results for these: {{ missing_info }}{% endif %}
{% if review_comment %}
Reviewer instruction (takes priority over the original requirement for missing values):
{{ review_comment }}
{% endif %}
