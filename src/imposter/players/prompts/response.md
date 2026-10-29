{% if retry_reason %}

Your previous answer in this turn was rejected: {{ retry_reason }}. Answer again and fix this.
{% endif %}
{% if response_schema %}

Answer with only a JSON object that matches this JSON schema, without code fences or any other text:

{{ response_schema }}
{% endif %}
