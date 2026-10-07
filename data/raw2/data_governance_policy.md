# Data Governance and Document Lifecycle Policy

- **Status:** Approved
- **Date:** 2026-05-01
- **Author:** Data Governance Office

## Purpose and Scope

This policy defines how organizational documents are classified, owned, approved, indexed, retained, and retired. It applies to technical specifications, business procedures, project records, training materials, support documentation, and internal policies.

## Ownership and Classification

Every managed document should have a business owner and a classification label such as Public, Internal, Confidential, or Restricted. The owner is responsible for accuracy and updates. Restricted documents must not appear in snippets or citations for unauthorized users. Missing ownership should trigger a review queue.

## Approval Lifecycle

Documents move through Draft, In Review, Approved, Archived, and Withdrawn states. Draft content should not normally override approved policy. Approval records should include approver, timestamp, version identifier, and effective date. Withdrawn documents should be excluded from normal search while remaining available to authorized auditors when retention rules permit.

## Retention and Deletion

Retention periods depend on document category and business requirements. The platform should support retention labels and review dates. Owners should decide whether content is retained, archived, anonymized, or deleted. Removal from active retrieval should be tracked separately from physical deletion.

## Quality Reviews

High-impact documents should be reviewed on a schedule. Policies and security procedures should be reviewed annually or after material changes. Search analytics can reveal failed queries, hard-to-find documents, and conflicting instructions. Analytics should be aggregated where possible.

## Governance Test Scenarios

Test that approved policy outranks a draft for current-process questions; withdrawn documents do not appear in normal search; restricted documents are invisible to unauthorized users; historical versions can be found by date; missing owner metadata creates a review flag; and deleted documents are removed from active retrieval.

## Detailed Test Scenarios

Scenario 01: Test a question about purpose and scope. Ask one direct question and one paraphrased question. Confirm the returned passage contains the answer, the citation points to the right section, and no unsupported details are added.

Scenario 02: Test a question about ownership and classification. Ask one direct question and one paraphrased question. Confirm the returned passage contains the answer, the citation points to the right section, and no unsupported details are added.

Scenario 03: Test a question about approval lifecycle. Ask one direct question and one paraphrased question. Confirm the returned passage contains the answer, the citation points to the right section, and no unsupported details are added.

Scenario 04: Test a question about retention and deletion. Ask one direct question and one paraphrased question. Confirm the returned passage contains the answer, the citation points to the right section, and no unsupported details are added.

Scenario 05: Test a question about quality reviews. Ask one direct question and one paraphrased question. Confirm the returned passage contains the answer, the citation points to the right section, and no unsupported details are added.

Scenario 06: Test a question about governance test scenarios. Ask one direct question and one paraphrased question. Confirm the returned passage contains the answer, the citation points to the right section, and no unsupported details are added.

## Questions for Retrieval Validation

Q1: What does the document say about purpose and scope?
Expected evidence: section 'Purpose and Scope'.
Validation: check top-3 and top-5 retrieval, source title, section label, and answer support.
Q2: What does the document say about ownership and classification?
Expected evidence: section 'Ownership and Classification'.
Validation: check top-3 and top-5 retrieval, source title, section label, and answer support.
Q3: What does the document say about approval lifecycle?
Expected evidence: section 'Approval Lifecycle'.
Validation: check top-3 and top-5 retrieval, source title, section label, and answer support.
Q4: What does the document say about retention and deletion?
Expected evidence: section 'Retention and Deletion'.
Validation: check top-3 and top-5 retrieval, source title, section label, and answer support.
Q5: What does the document say about quality reviews?
Expected evidence: section 'Quality Reviews'.
Validation: check top-3 and top-5 retrieval, source title, section label, and answer support.
Q6: What does the document say about governance test scenarios?
Expected evidence: section 'Governance Test Scenarios'.
Validation: check top-3 and top-5 retrieval, source title, section label, and answer support.
