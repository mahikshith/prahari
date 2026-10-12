# India regulation and residency: pilot scoping

**Reviewed: 2026-10-12.** This records primary-source research and proposed product requirements, not a legal certification or a shipped-feature inventory. Customer counsel must confirm applicability, contracts and later notifications before procurement or deployment. Current implementation scope is in [DECISIONS.md](DECISIONS.md).

India deployment is a useful customer requirement. **DPDP does not impose universal India-only storage.** Section 16 permits country-specific transfer restrictions and preserves stricter laws. Future Rules 13(4) and 15 add specified-data restrictions for Significant Data Fiduciaries and government-order conditions, respectively; they do not make every overseas AI call unlawful. [DPDP Act, s16][act]; [final Rules, rr13 and 15][rules].

## Enacted rules versus commenced duties

The Act received assent on 11 August 2023. Final Rules G.S.R. 846(E) and commencement notification G.S.R. 843(E) are dated 13 November 2025. As of this review, the main Data Fiduciary duties remain scheduled for 2027. [Act][act]; [commencement notification][commencement]; [Rules, r1][rules].

| Date | Tranche | Status on review date |
| --- | --- | --- |
| 13 November 2025 | Definitions, Board/machinery provisions; Rules 1, 2, 17–21 | Commenced |
| 13 November 2026 | Act s6(9), s27(1)(d); Rule 4 on Consent Managers | Scheduled |
| 13 May 2027 | Main scope, lawful-processing, rights, security, breach and transfer duties; Rules 3, 5–16, 22–23 | Scheduled |

These dates follow the Gazette calendar; the MeitY portal upload date is 14 November 2025. Official [PIB reporting in June 2026][pib] and [NeGD guidance in October 2026][negd] corroborate 13 May 2027. Use the notifications' exact section lists for legal implementation, and recheck amendments before launch.

The [10 December 2025 corrigendum][corrigendum] corrects Rules wording. The [5 October 2026 Removal of Difficulties Order][order] clarifies disability and data-audit wording in Act ss9–10. Neither changes the phased timetable.

Future Rule 7 requires breach intimation without delay to affected individuals and the Board, followed by detailed Board information within 72 hours, subject to an allowed extension. Rules 6(1)(e) and 8(3) contain one-year retention provisions for relevant personal data/logs. These are distinct from today's CERT-In duties; a blanket 180-day deletion policy will not resolve both. [Final Rules][rules].

## Applicability matrix

| Regime | Who/data to assess | Relevant requirement | Prahari consequence |
| --- | --- | --- | --- |
| DPDP | Digital personal data; customer/Prahari roles depend on purpose and means | Core duties scheduled as above; identifiers can be personal data; no universal localization | Record roles, purpose, processor terms and applicable transfer rules. [Act, ss2–8 and 16][act] |
| CERT-In | Covered service providers, intermediaries, data centres, bodies corporate and government organizations | Annexure I incidents reported within six hours of notice; secure rolling 180-day ICT logs in Indian jurisdiction | Preserve usable incident evidence and an accountable escalation path. [28 April 2022 Directions, paras(ii), (iv)][cert] |
| RBI payment-system data | Authorized payment-system providers and relevant payment-chain arrangements; end-to-end payment data | India-only storage with specified foreign-leg exceptions; offshore processing has return/deletion conditions | Determine whether collected fields include regulated payment data; AI spend totals alone do not establish this scope. [6 April 2018 circular][rbi]; [26 June 2019 FAQ][rbifaq] |
| SEBI cloud framework | Listed regulated entities adopting cloud services | India storage/processing, logs and DR; CSP/underlying infrastructure selection and audit requirements | Review the customer's entity, deployment and full supply chain before offering a hosted service. [6 March 2023 framework, Principles 2–3][sebicloud] |

CERT-In FAQ Q35 permits logs to be stored outside India **also**; it does not justify omitting the Indian-jurisdiction requirement. FAQ Q37 makes the required log set dependent on systems/sector. A Prahari cost database alone is not proof of complete ICT-log coverage. [CERT-In FAQ][certfaq].

RBI's FAQ permits overseas processing subject to deletion abroad and return to India within one business day or 24 hours, whichever is earlier, with specific cross-border transaction treatment. This payment-specific rule must not be generalized to all AI metadata. [RBI FAQ][rbifaq].

**SEBI nuance:** the 2024 CSCRF originally described an exception for qualifying IT/cybersecurity data sent to global SOCs or cybersecurity SaaS, with classification, approval and availability conditions. [CSCRF, PR.DS.S2, p107][cscrf]. Its localization standard was then placed in abeyance until further notification. [31 December 2024 clarification, para2.3][sebiabeyance]. The [28 August 2025 clarification, Table1][sebitechnical] still labels relevant controls in abeyance. This review has not established a later reinstatement or resolved its interaction with the separate cloud framework; do not encode an automatic overseas-export exemption. The [June 2025 FAQ, Q26][sebifaq] separately says encryption keys and key-management operations must stay in India. An “India region” label is insufficient evidence.

## Model endpoints and evidence

| Provider example | What the official documentation supports | What Prahari should record |
| --- | --- | --- |
| Google model endpoints | Global requests may be processed anywhere; selected storage location is separate. Processing commitments vary by model/location. Global does not mean “definitely US.” [Google residency documentation][google] | Endpoint, model/version, configured location and dated contractual processing/storage commitment |
| Amazon Bedrock | Cross-region inference may process outside the source region; CloudTrail `additionalEventData.inferenceRegion` identifies the processing region. [AWS documentation][aws] | Inference profile, source region and observed destination region where available |
| Azure Foundry | Global and data-zone deployment types have different processing boundaries; an APAC zone spans multiple regions. [Microsoft documentation][azure] | Deployment type/model, supported geography/zone and current contractual boundary |

An API hostname, caller IP, billing-resource region or service-account identity alone does not prove physical inference, storage or support-access location. Cost/audit sources may omit those facts. Keep **configured**, **provider-guaranteed**, **observed**, and **unknown** evidence separate, with source, collection time and coverage. A residency finding should state the policy it conflicts with and its evidence; missing evidence should remain unknown.

## Product requirements and pilot evidence

The following are proposed acceptance criteria, not claims that the current collector implements them:

1. **Minimize collection.** Default to usage/cost/security metadata. Exclude prompts, completions, secrets and raw provider bodies. Allowlist extension fields; review identifiers and outbound evidence individually.
2. **Review the complete dataflow.** Map model requests, collector/database, billing/audit sources, caches, backups, DR, encryption/key management, Slack/email, error reporting and support exports. Record each processor, purpose, country/boundary, access path and retention rule. Customer-owned India infrastructure covers only part of this map.
3. **Constrain outbound paths.** Customer-held credentials, restricted destinations and minimal alert content are the starting posture. Test actual notification bodies and support bundles; country flags must not imply that every subprocess stays in India.
4. **Separate identity from accusation.** Employee email/ID or linkable pseudonyms can remain personal data. Section 7(i) provides an employment/safeguarding legitimate-use route; it is not a blanket approval for surveillance. Have counsel document the purpose/basis, access and employee communication. A shared account cannot establish which employee made a request. [Act, ss2, 4 and 7(i)][act]
5. **Set retention per dataset.** Record minimum/maximum periods, purpose, legal hold and erasure process separately for identity mappings, cost records, operational logs and incident evidence. Test access restrictions, export, backup lifecycle and deletion after authorized retention.
6. **Measure incident readiness.** Preserve UTC timestamps, first source availability, alert delivery and response evidence. Assign a human incident owner and test the escalation clock. A spend anomaly alone does not establish a reportable breach; a dashboard does not perform statutory reporting.

## Questions to resolve with each design partner

- Which entity, sector rules, contractual localization obligations and regulated datasets apply? Are systems subject to multiple regulators, and which current SEBI controls apply?
- Is the customer the Data Fiduciary and Prahari solely its processor, or does Prahari determine additional purposes? What existing IT Act/SPDI obligations apply during the transition?
- Which exact models/features guarantee India processing and storage? What are the backup, abuse-monitoring, retention, remote-support and subprocessor exceptions?
- Which fields can identify people or expose payment/regulatory data? Can alert delivery and support remain inside the customer's approved boundary?
- Have later country restrictions, SDF designations, specified-data orders or sector amendments changed the reviewed position?
- Who approves retention, lawful basis and regulator/individual notification, and what evidence is required before any compliance claim?

[act]: https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf
[rules]: https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf
[commencement]: https://www.meity.gov.in/static/uploads/2025/11/c56ceae6c383460ca69577428d36828b.pdf
[corrigendum]: https://www.meity.gov.in/static/uploads/2025/12/3c7ebbae0e5456f493f486e6845df86b.pdf
[order]: https://www.meity.gov.in/static/uploads/2026/10/daf495a7b5798a3dfa72a944b51fc176.pdf
[pib]: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2261823&lang=1&reg=3
[negd]: https://negd.gov.in/events/dpdp-act-readiness-workshop-b2b-and-b2c-implementation/
[cert]: https://www.cert-in.org.in/PDF/CERT-In_Directions_70B_28.04.2022.pdf
[certfaq]: https://www.cert-in.org.in/PDF/FAQs_on_CyberSecurityDirections_May2022.pdf
[rbi]: https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=11244&Mode=0
[rbifaq]: https://systemhealth.rbi.org.in/Scripts/FAQDisplay.aspx_Id%3D130%281%29.html
[sebicloud]: https://www.sebi.gov.in/sebi_data/attachdocs/mar-2023/1678112480131.pdf
[cscrf]: https://www.sebi.gov.in/sebi_data/attachdocs/aug-2024/1724326790365.pdf
[sebiabeyance]: https://www.sebi.gov.in/sebi_data/attachdocs/dec-2024/1735646756843.pdf
[sebitechnical]: https://www.sebi.gov.in/sebi_data/attachdocs/aug-2025/1756380695925.pdf
[sebifaq]: https://www.sebi.gov.in/sebi_data/faqfiles/jun-2025/1749647139924.pdf
[google]: https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/data-residency?content_language=English
[aws]: https://docs.aws.amazon.com/en_en/bedrock/latest/userguide/cross-region-inference.html
[azure]: https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/deployment-types
