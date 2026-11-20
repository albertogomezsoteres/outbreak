# Limitations, failure modes, misuse and deployment

## Validity limitations
- **Synthetic but realistic tasks.** The repos are small (five to ten files) and the API is simulated. Real
  codebases offer more ways out, and more noise around the note. Absolute rates should not be extrapolated
  to production. Contrasts between models, traits and defenses are the object of study.
- **Scripted prefix.** Agents always read the board at the decision point. In the wild many agents never look,
  which lowers exposure. Our rates are *conditional on exposure* by design.
- **One note, one channel.** Real teams have many channels: chat, docs, commit messages, memory. The board is
  one append-only channel with a 20-post window.
- **Homogeneous teams in Act 4.** Each outbreak uses one model. Mixed teams may spread less, as The Troy Moment
  found mixed teams diagnose contradictions more often.
- **Provider variance.** OpenRouter routes a model id to different providers, with possibly different
  quantizations and chat-template handling. The provider is stored per response, and analyses can stratify by
  it. The white-box model (local weights, our template rendering) may not behave exactly like the API-served
  model, so the closed-loop check is run on the local model itself.
- **Reasoning effort fixed at "low".** Propensities may change with more deliberation.
- **Models change.** API models are updated silently. The cache freezes *our* samples, but a replication
  months later is a new measurement.
- **The pilot is not confirmatory.** It used a different harness (DEVIATIONS.md). Two pilot rows (DeepSeek,
  GLM) were reported but their logs were lost.

- **LLM raters and writers.**
  - The manipulation check uses one LLM rater. Kappa with the design is reported, but the rater can share
    blind spots with the agents.
  - Natural notes come from a single writer model in six voices. That is broader than the templates, but it
    is not the full range of what agents post. Agent-written posts from the outbreaks are the third,
    fully organic test set.

## Statistical caveats
- Rare events make logit trait models fragile under separation. Linear-probability risk differences with
  note-clustered SEs are the primary trait estimate for that reason.
- Common random numbers make paired outbreak tests powerful but correlated across arms. Holm controls the
  family-wise error rate within H4, not across all hypotheses in the project.
- The filter's in-distribution scores are inflated by shared sentences between generated notes. The leakage
  report quantifies this, and agent-written posts from outbreaks are the out-of-distribution check.
- The probe predicts *propensity at a prefix*. It cannot predict an individual sampled outcome better than
  that propensity allows.

## Failure modes of the defenses
- **Channel defenses** only see the board. They cannot stop an agent that rediscovers the shortcut alone (the
  `no_board` arm measures that floor). A filter trained on our note grammar may miss paraphrases by real
  agents. An LLM judge may over-block legitimate tips, which the benign notes measure.
- **Action monitors** see one call plus a short context. A violation split across innocent-looking calls (a
  script that edits tests) evades argument-level checks. Our detectors still catch it after the fact; a
  deployed monitor might not.
- **Vaccines** are model- and layer-specific. Steering can degrade unrelated capabilities beyond what our
  utility checks measure, and a direction learned on four mechanisms may not transfer to new ones.

## Misuse risks and mitigations
- **A recipe for persuasive bad advice.** The trait effects show which rhetoric makes harmful tips spread
  between agents. *Mitigation:* the notes are mundane workplace tips about fictional infrastructure, with no
  real credentials or systems, and the same results directly inform filters and policy (which channels to
  screen, what to flag). This is standard dual-use red-teaming and is published together with the defenses.
- **Overconfidence in defenses.** A good frontier in our environment is not a guarantee elsewhere. The README
  presents defense results as *relative* comparisons under stated conditions.
- **Named-model comparisons.** Susceptibility is reported per model version and date, with CIs. Results
  describe a configuration (model, provider, reasoning effort, prompt), not an intrinsic property of a vendor.

## Stakeholders
- **Teams deploying multi-agent coding systems.** They decide where to put guardrails and what shared channels
  to allow.
- **Model developers.** Susceptibility to peer-suggested policy violations is a training and evaluation target.
- **Security and compliance owners.** Credentials, production access and data integrity are their concern;
  agents are a new insider-risk class.
- **People affected by fabricated data or broken tests downstream.** Finance teams reading a report built from
  fabricated numbers, for example.

## Deployment considerations
- The channel filter ships as an HTTP service (`outbreak serve`) and is meant for **flag-and-hold**, not silent
  deletion. Held posts go to a human or a stronger reviewer.
- Calibrated scores let operators pick a threshold that fits their false-positive budget. The threshold is
  chosen on benign posts at a target FPR.
- Probes and vaccines need white-box access, so they apply to self-hosted open-weight agents only.
- Log the evidence-based detectors (canary tokens, provenance) in production too. They are cheap, they need
  no model, and they are the ground truth everything else is measured against.

## Future work
- Mixed-model teams, and many channels including long-term memory.
- Notes that agents themselves write (the outbreak data already contains them) as a harder test set for filters.
- Training-time interventions, such as fine-tuning on resisting peer shortcuts, compared with the vaccine.
- Agents that *correct* the board, for example by posting "this is against policy", as a herd-immunity
  mechanism.
- Replication on a large susceptible open-weight model, with SAE features instead of diff-of-means.
