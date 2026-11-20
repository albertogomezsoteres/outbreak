# Related work and positioning

Outbreak brings together five lines of work. For each one, this note says what we borrow and what is new.

## 1. Shortcut-taking ("cheating") by single agents on impossible tasks
**ImpossibleBench** (Zhong, Raghunathan & Carlini, arXiv:2510.20270, ICLR 2026) builds *impossible* variants of
coding tasks by making unit tests contradict the specification, so any pass implies a specification-violating
shortcut. It shows that frontier models frequently cheat, that context engineering changes cheating rates,
and that LLM monitors catch 86–89% of attempts on simple tasks but only 42–65% on SWE-bench-style tasks.

*Borrowed:* the impossible-task logic. Our mechanism M1 (a stale test that contradicts the spec) is a direct
analogue. Like ImpossibleBench, we also build matched possible variants to measure utility.
*New:* we do not study *spontaneous* cheating. We study cheating that is **socially transmitted**: the same
impossible task with and without a peer's note. We also add three non-test shortcuts that matter in
production: credentials (M2), off-limits infrastructure (M3) and data fabrication (M4). Every one of them is
detected from evidence (canary token, host, file hash, provenance), not by a monitor.

## 2. Peer information at the decision point
**The Troy Moment** (Zhang, arXiv:2609.15494, Sep 2026) is the closest work. Its agents face
ImpossibleBench repair tasks, and a shared board carries peer edits (punished or unpunished) and forged
authorization claims. Three frontier models mostly treated peer precedent as non-authorizing. The board
mainly carried *evidence* (post → verify → act) rather than copied actions. The paper explicitly does **not**
model cascades over rounds. It does not inject adversarial peer messages that advocate crossing the boundary,
evaluates no defenses, and uses no white-box analysis.

*New here:* each of those four gaps is one of our "acts":
- adversarial peer notes with a factorial of rhetorical traits (Act 1);
- white-box prediction of the decision (Act 2);
- a steering intervention (Act 3);
- multi-round outbreaks with defenses at three levels (Act 4).

Our pilot agrees with Troy where the two overlap: some models resist peer notes entirely (gpt-5-nano, 1/60).
It also adds the missing contrast: an open-weight model (gpt-oss-20b) is strongly susceptible (14/80 vs 0/80).

## 3. Infection in multi-agent systems
- **Agent Smith** (Gu et al., ICML 2024, arXiv:2402.08567) introduces *infectious jailbreak*: one adversarial
  image placed in a single agent's memory spreads to (almost) all of up to one million LLaVA agents,
  exponentially fast, through randomized pairwise chat.
- **Prompt Infection** (Lee & Tiwari, arXiv:2410.07283) shows self-replicating LLM-to-LLM prompt injection
  inside multi-agent systems, and proposes *LLM Tagging* as a defense.
- Surveys of agent memory frame shared-memory contamination as social contagion.

*Difference:* those payloads are **adversarial artifacts**: optimized images, or injected instructions that
hijack the agent. Our "pathogen" is mundane. It is a plausible teammate tip that names a real shortcut, read
by an agent that is genuinely blocked. No optimization or jailbreak string is involved. The harm is a policy
violation the agent *chooses* because it seems helpful, which matches how engineering teams actually leak bad
practice. We also measure the spread with evidence-based detectors, inside realistic tool-using tasks.

## 4. Social influence and persuasion
The six note traits come from classic influence research and its LLM counterparts. Social proof and
authority are Cialdini's principles. Urgency stands in for scarcity and time pressure. Actionability and
justification come from work on compliance with instructions.

Work on conformity and herd behavior in LLM agents shows that agents shift answers toward their peers. We
turn this into a **causal, factorial** test of which rhetorical features make a *policy-violating* tip
contagious. Each trait is randomized independently, paraphrases are randomized independently, and length is
controlled.

## 5. Linear representations, probes and steering
- **Representation engineering** (Zou et al., arXiv:2310.01405), activation addition (Turner et al.,
  arXiv:2308.10248) and contrastive activation addition (Rimsky/Panickssery et al., arXiv:2312.06681) show
  that behaviors can be read and steered along linear directions.
- **Refusal is mediated by a single direction** (Arditi et al., arXiv:2406.11717).
- **Persona vectors** (Chen, Arditi, Sleight, Evans & Lindsey, arXiv:2507.21509) extract trait directions
  (evil, sycophancy, hallucination) from natural-language descriptions. They use them to monitor persona
  shifts and to apply *preventative steering*.
- Linear probes can flag deceptive "sleeper" behavior from activations (MacDiarmid et al., 2024).

*Borrowed:* the diff-of-means direction, residual-stream interventions, and random-direction controls.
*New:* we apply them to a **behavioral decision in an agentic, multi-turn, tool-using setting**: whether an
agent at the decision point will take a socially suggested shortcut.

Our label is the empirical propensity, measured over many sampled continuations from that exact prefix.
That gives the probe a real target, not a proxy. We also require the probe to beat a strong baseline:
knowing *which note* was read. Finally, we check the vaccine in closed loop, on real episodes graded by the
environment's detectors.

## 6. Monitoring and control
AI-control work (Greenblatt et al., arXiv:2312.06942) treats monitors as defenses that must be judged under a
usefulness budget. ImpossibleBench reports what LLM monitors detect.

We compare three **placements** of the guardrail on the *same* outbreaks, with common random numbers:

1. the communication channel (LLM judge, or a trained filter that learns from consequences);
2. the action (an LLM monitor that can veto a tool call, against a detector-based oracle as the upper bound);
3. the model's internals (probe and vaccine).

Each placement is reported as a full safety–utility frontier.

## One-sentence positioning
> Prior work shows that agents can cheat on impossible tasks (ImpossibleBench) and that adversarial payloads
> can spread between agents (Agent Smith, Prompt Infection). Outbreak shows **which** agents catch an ordinary
> policy-violating tip from a peer, **which features** of the tip make it contagious, **what the model's
> hidden state reveals before it acts**, and **where a guardrail stops the spread at the least cost to
> useful work**.
