# English demonstration script — target 2:40

Record with labelled synthetic data. Use the frontend simulator if it is the verified demonstration route; explicitly say “simulated Alexa interaction” rather than claiming a live Alexa integration. Keep the output and narration synchronized; replace placeholders only after a recorded rehearsal.

| Time | Screen/action | Narration |
|---|---|---|
| 0:00–0:15 | Purr Nanny today view, sample banner visible | “Purr Nanny helps a household keep one shared record of their cat’s care and health observations. This demonstration uses sample data.” |
| 0:15–0:45 | Record observation, show follow-up, supplement same event | “I record that Luna vomited. Purr Nanny asks for missing details instead of assuming they are normal. My answer updates the original observation. A retry does not add a duplicate.” |
| 0:45–1:10 | Today view with family feeding event | “The household can check today’s feeding and care records. We retain who reported the observation and when it happened. Access is scoped to the household by the server.” |
| 1:10–1:35 | Patterns and insufficient-data example | “These patterns are calculated from recorded observations. Each result includes its window, sample size and evidence. When there is too little information, Purr Nanny says so. It does not infer a diagnosis or claim that a food change caused a symptom.” |
| 1:35–2:05 | Synthetic emergency signal, notification status | “This synthetic example reports straining with little or no urine. The priority signal appears before routine questions. Notification status is explicit: provider acceptance does not prove that a family member received or read a message.” |
| 2:05–2:30 | Veterinary summary | “The veterinary view presents the same facts and evidence as the service. Occurrence times, source labels and missing details stay visible. It is a record for discussion with a veterinarian.” |
| 2:30–2:40 | Architecture and limitations | “The rule package runs independently from AWS and Alexa. Current integration and review limitations are documented alongside the code.” |

Before recording: run seed/reset in a disposable database; verify fixed reference time; disable real SMS or use an explicitly approved recipient; clear personal details; confirm sample banner; rehearse exact outputs. Record actual enabled capabilities only. A polished MP4, accessible video URL and measured duration remain pending.
