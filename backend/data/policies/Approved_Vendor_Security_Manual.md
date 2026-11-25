# Approved Vendor Security Manual

> **Status:** Sample policy content for this application. It is not an approved
> corporate security standard. The organization must review and replace it with
> its approved requirements before relying on it for real purchasing decisions.

## 1. Purpose and scope

This manual describes security checks for suppliers that provide products or
services to the organization. Apply the checks before onboarding a supplier,
starting a trial that uses corporate accounts or data, granting access, or
renewing a material service. The depth of review should match the supplier's
access, data sensitivity, service criticality, and the consequences of an outage.

An approved-vendor status is not a blanket approval for every product or use.
Confirm that the specific supplier, catalog item, service, and intended use are
approved in the authoritative procurement system.

## 2. Roles and review

- **Requester:** describes the business need, data involved, users, integrations,
  and required access.
- **Procurement:** confirms supplier and catalog eligibility, commercial
  ownership, and required purchase approvals.
- **Information Security:** assesses security evidence and required safeguards
  when the supplier will access systems, handle organizational data, or support
  a critical service.
- **Privacy and Legal:** review personal-data processing, cross-border transfers,
  contract terms, and other matters requiring their expertise.
- **Service owner:** approves the operational design, assigns an owner, and
  monitors the supplier for the life of the service.

Do not treat a questionnaire, certificate, or audit report as proof that every
control is effective. Review the scope, date, exceptions, and relevance of the
evidence; request follow-up where gaps affect the proposed use.

## 3. Due diligence before access

Before granting production access or sharing non-public data, document the
supplier's services and data flows, hosting locations, subprocessors, identity
and access model, incident process, resilience arrangements, and deletion
process. Request current independent assurance or equivalent evidence
appropriate to the assessed risk.

Record material findings, required mitigations, the accountable owner, and any
accepted residual risk. Unresolved high-impact findings must be escalated to
Information Security and the service owner before access or purchase. A
commercial approval does not waive a security review.

## 4. Minimum safeguards

Contracts and service configurations should require safeguards appropriate to
the data and service, including:

- unique user identities, least-privilege access, and multi-factor
  authentication for privileged or remote access;
- encryption in transit and at rest, with key access restricted to authorized
  personnel;
- timely security updates, vulnerability handling, and secure configuration;
- access logging and the ability to investigate relevant security events;
- tested backup, recovery, and continuity arrangements for critical services;
- documented incident escalation, cooperation, and evidence preservation; and
- return or secure deletion of organizational data when the service ends.

Document exceptions and compensating controls. Do not place regulated,
confidential, or otherwise restricted information in a supplier service until
the required security, privacy, and contractual reviews are complete.

## 5. Ongoing oversight and incidents

The service owner and Information Security should reassess a supplier when
there is a material change to its ownership, service, hosting, data use,
subprocessors, or security posture. Review assurance evidence at a cadence
proportionate to risk and before material renewals.

Report suspected supplier-related incidents through the organization's security
incident process immediately. The supplier agreement must define notification
and cooperation obligations; do not assume that a vendor's public status page
replaces direct incident reporting.

## 6. Restricted and offboarded suppliers

### 6.1 Sanctioned, blocked, or ineligible suppliers

Do not create a requisition, grant access, or make a commitment to a supplier
marked blocked, sanctioned, or otherwise ineligible in the authoritative vendor
and compliance records. Stop processing and refer discrepancies or appeals to
Procurement, Compliance, and Information Security. A similar name or a proposed
reseller is not evidence that the restriction can be bypassed.

For this sample application, the input guardrail includes example blocks for
ShadowSupply, RogueIT, Apex Grey Market, and QuickCash Electronics. These
examples are not a complete or authoritative sanctions list. Production
eligibility decisions must use current organization-approved records.

### 6.2 Offboarding

At termination or transition, revoke supplier identities, credentials, tokens,
and network access; recover organization assets; and obtain confirmation of data
return or deletion as required by the agreement. Preserve records needed for
audit, legal hold, or incident response.
