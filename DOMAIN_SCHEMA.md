# Domain Schema: Municipal Transit Incidents

This form collects information about incidents that affect public transportation services.
## Fields

| Field Name | Purpose | Required |
|---|---|---|
| incidentTitle | A short title identifying the transit incident | Yes |
| routeLine | The bus route or transit line affected by the incident | Yes |
| submitterEmail | The email address of the person reporting the incident | Yes |
| description | Detailed information about what happened | Yes |
| category | The type of transit incident | Yes |
| termsAccepted | Whether the submitter accepted the terms and conditions | Yes |
| submissionDate | The date and time added after a successful submission | Generated |

## Category Values

1. Delay
2. Collision
3. Service Suspension
4. Infrastructure Issue