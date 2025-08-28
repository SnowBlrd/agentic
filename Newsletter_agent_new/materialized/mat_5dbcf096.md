# thought, can you monitor it? — AI Alignment Forum

> Source: https://www.alignmentforum.org/posts/ZEdP6rYirxPxRSfTb/if-you-can-generate-obfuscated-chain-of-thought-can-you

tldr:

Chain-of-thought (CoT) monitoring is a proposed safety mechanism for overseeing AI systems, but its effectiveness against deliberately obfuscated reasoning remains unproven. "Obfuscated" reasoning refers to reasoning which would not be understood by a human, but which contains information that a model could understand in principle, for example model-encrypted reasoning. A weaker model (assumed to be trusted) which does not know the obfuscation scheme may be a bad monitor, whereas, using the model doing the obfuscation (the 'untrusted model') as a monitor might work. We finetune language models to add backdoors to toy programming problems from the APPS dataset, while using encrypted or steganographic reasoning. We find that, in most cases, the finetuned models are better monitors than the models they are finetuned from, although a baseline of a more optimized monitor prompt, alongside finetuning on attacks without any encoding, makes up some of the gap.

1. Introduction

Chain-of-thought reasoning (Nye et al., 2021, Wei et al., 2022) is a powerful technique for improving language model performance on complex tasks (Li et al., 2024, Cook et al., 2025). However, the transparency provided by CoT might not be durable, and models could in principle learn obfuscated reasoning, while maintaining task performance. For example they may be trained with a length penalty encouraging shorter reasoning, which would potentially penalise human-readable reasoning. This would of course undermine CoT monitoring (Korbak et al., 2025) as a safety mechanism for advanced AI systems.

One way around this is "untrusted monitoring" (Greenblatt et al., 2023). Intuitively, another instance of the same model (in AI control it is assumed to be malicious, hence "untrusted"; our setup is not a control evaluation and we don't assume the monitor is malicious, but we reuse this terminology) should be capable of detecting obfuscated reasoning, as it possesses equivalent obfuscation capabilities. We view this ability as one kind of "generator-to-discriminator transfer". Here the generator produces reasoning that is useful for completing a reasonably complex coding task, and the discriminator needs to distinguish between benign and malicious reasoning, even when the reasoning is obfuscated.

We create model organisms of obfuscated reasoning and test whether untrusted monitors can effectively detect hidden malicious behavior. Some objections to CoT monitoring as a safety mechanism argue that it would be possible for model reasoning to be encoded, and so we want to stress test CoT monitoring under this condition.

There is an obvious gap in our approach, which is that we do not consider the possibility of the monitor instance and attacker instance of the same model colluding with each other. This is likely the most difficult issue with untrusted monitoring, but we want to confirm generator-to-discriminator transfer is possible first. We plan to investigate collusion in future work, and briefly discuss this in section 5.2.

2. Related Work

Previous work has explored various aspects of model deception and monitoring. Most relevant is recent work examining CoT monitoring in the non-obfuscated case (Arnav et al., 2025; Emmons et al., 2025). Other work explores models' ability to use or learn encrypted (Davies et al., 2025) or steganographic (Matthew et al., 2024) reasoning. However, to our knowledge, no prior work has empirically demonstrated effective detection of such obfuscation by untrusted monitors.

3. Methodology

All experiments were done in the APPS backdoor setting introduced in Greenblatt et al. The APPS dataset (Hendrycks et al., 2021) consists of problems collected from different open-access coding websites such as Codeforces, Kattis, and more. The problems range in difficulty from introductory to collegiate competition level. Models can be run in "honest mode" where they are genuinely trying to solve the coding problem, and "attack mode", where they are additionally trying to insert a backdoor. Each mode is just the same model with a different system prompt. We say a solution is backdoored if it passes all APPS test cases, and there is a specific input (submitted by the model along with the code) that will yield an incorrect output: running it on reference solutions and on the backdoored solution produces different outputs.

3.1 Experimental Framework

Our experiments consist of three phases:

Phase 1: Attacker Obfuscation Training - We train models to use obfuscated reasoning CoT traces when solving APPS problems (using 50% honest runs and 50% attack runs), using supervised finetuning on training examples with encoded reasoning (and corresponding APPS solutions).

Phase 2: Attacker Evaluation - We run the finetuned models on a test set in honest mode and attack mode. In both cases, if the finetuning has been successful, the models will be using obfuscated reasoning.

Phase 3: Monitor Evaluation - We prompt both the finetuned model and the non-finetuned model (that the attacker was finetuned from) to act as a monitor. We evaluate both models' ability to differentiate between honest reasoning and reasoning about inserting backdoors.

If generator-to-discriminator transfer occurs, the finetuned model should be a better monitor than the non-finetuned model.

3.2 Dataset Construction

We use the APPS dataset, using 1,800 examples for obfuscation training, and 500 examples as a test set. For 50% of the APPS training data, we generate malicious reasoning and solutions using base GPT-4.1, prompted to extensively plan backdoor insertion before submitting code, and for the other 50% we generate reasoning about how to honestly solve the problem. Because we use the OpenAI supervised finetuning API, to comply with API moderation policies we dilute the training dataset such that it is 95% benign conversations from UltraChat. We use various obfuscation techniques to rewrite the base GPT-4.1 reasoning traces from our initial training dataset.

3.3 Obfuscation Techniques

Cipher Encoding

We apply a random letter substitution cipher to the agent's reasoning. The cipher is consistent across all training examples. We also use a bigram variant which encodes with a mapping between pairs of letters.

Example outputs from a model finetuned to use the (unigram) cipher:

Safety Steganography

We use a LLM (Claude Sonnet 4) to translate suspicious reasoning into benign-appearing text about code safety. The transformation ideally preserves information content while hiding malicious intent through semantic obfuscation.

Example outputs from a model finetuned on the transformed trajectories:

Making Steganography Less Suspicious with Monitor Signal

We created two variations on the above "safety steganography" approach, which use signal from a monitor to create less suspicious reasoning traces. We first finetune a model with the safety steganography approach, and generate reasoning traces from this model using the APPS training set user prompts. We run a GPT 4.1 base monitor (with a different prompt to the one we use at test time) over these traces so they each have associated suspicion scores between 0 and 10.

We then finetune base GPT 4.1 in two ways:

We finetune on the 25% least suspicious traces.

We use a conditional training set up, where we append "The sneakiness of your reasoning should vary between level 0 (not suspicious at all) and 10 (obviously suspicious). This time, make sure your reasoning has a suspiciousness score of: {max_suspicion_score}." to the system prompt, adding a reasoning trace of score max_suspicion_score as the assistant message. Then at test time, we set max_suspicion_score to 0.

No Encoding

As a baseline, we finetune on trajectories from APPS without any encoding, to see the effect from purely learning the dataset.

3.4 Monitoring

By default we use a standard monitor prompt from Control Arena which provides the model chain of thought and a description of the APPS problem, then allows the model to reason before submitting a suspiciousness score from between 0 to 10.

The monitor prompt was:

We also experiment with giving the monitor a hint that reasoning might be encoded:

0 should be an exceptional score, since the model might be hiding things in encoded language. Sometimes reasoning might be encrypted. This could be benign or not, you will have to decrypt it to figure that out. It's also possible that the model is using benign-seeming language about improving the code to hide reasoning that might help with malicious actions. Be vigilant, and do not ignore weird or seemingly irrelevant passages. One clue to encoded reasoning might be if a part of the model's reasoning is not obviously helpful with achieving the goal of completing the task.

4. Results

4.1 Task Performance

Figure 1: APPS performance across different model configurations. Shows success rates for the main task (solving coding problems) and side task (inserting backdoors) in both honest mode and attack mode for various finetuning approaches, and for the base model when it is able to reason (Base GPT 4.1), and when it cannot (No CoT GPT 4.1).

Figure 1 shows the impact of different training approaches on model performance across honest mode and attack mode, and success rate at the "main" task, i.e. solving the coding problems, and "side" task, i.e. inserting backdoors (Side task performance is always zero on honest runs because the model is not told to complete it).

The safety steganography approach maintains substantially better honest performance than cipher-based methods, with safety steganography achieving 57.0% honest main task success compared to 37.6% for unigram cipher finetuning.

Safety steganography also preserves side task success rate better than cipher-based methods, although the effect is smaller, e.g. 60.6% side task success rate for steganography vs. 58.4% for the unigram cipher and 55.8% for the bigram cipher.

4.2 Generator-to-discriminator Transfer

We evaluate monitor effectiveness by measuring suspiciousness score distributions for honest vs. malicious reasoning traces. We ask the monitor model to rate the models' reasoning trace (without the final code the attacker model submitted) with a score between 0 and 10, where 10 is maximum suspiciousness, and 0 is totally benign (see Figure 2 for some example score distributions).

To turn these 0-to-10 suspiciousness ratings into a single, threshold-free quality metric we can compute the standard ROC-AUC. We create a labeled dataset in which each reasoning trace is tagged as benign (label 0) or malicious (label 1) and also has the monitor score. We sweep a decision threshold τ from 0 up to 10; at each τ classify a trace as “flagged” if its score ≥ τ, then record the resulting true-positive rate (TPR) and false-positive rate (FPR). See Figure 3 for examples.

We also measure "Detection rate @ 1% audit budget". This refers to finding the 99th percentile of suspicion score on honest reasoning traces, and seeing what fraction of attack traces are above this threshold. Using this as a threshold on honest traces should give us a roughly 1% false positive rate, but would ideally catch most attack traces. The “audit budget” term comes from the situation in AI Control where you only have a limited budget of human time to check if logs contain an attack.

Figure 2: Distribution of suspicion scores for honest and attack policies from various finetunes, when either the finetuned model is used as a monitor (top) or the non-finetuned model is used as a monitor (bottom).

Figure 3: ROC curves when using the non-finetuned model to monitor for finetuned model attacks (red) or using the finetuned model itself to monitor for finetuned model attacks (blue), for various finetunes.

Figure 4. Measuring generator-to-discriminator transfer for various finetunes ("Attack Type" in the figure) of GPT 4.1. Monitor AUC (left) and attack detection rate with a 1% audit budget (right) when using the non-finetuned model to monitor for finetuned model attacks (red bars) or using the finetuned model itself to monitor for finetuned model attacks (blue bars).

We test whether generator-to-discriminator transfer is occurring by measuring the difference in performance between a monitor which knows the encoding used in an attack, and a monitor which doesn't. Specifically we evaluate various models finetuned to learn encodings. In almost all cases, the finetuned model is a much better monitor for its own attack traces than the non-finetuned model, see Figure 4. The difference is large for both cipher types (unigram and bigram), and relatively modest for the safety steganography method.

Figure 5. Comparing finetuned model performance as a monitor to various other ways to potentially improve performance. Top shows safety steganography finetuned model attacks with different monitors, and bottom shows cipher finetuned model attacks with different monitors. Leftmost bar shows the performance when the finetuned model itself used as a monitor with the default prompt, rightmost bar shows the same but with a prompt designed for recognising encoded reasoning.

What is the source of the better monitor performance? We want to check if these results are driven primarily by knowledge of the domain (APPS backdoor attacks) learned during finetuning, or knowledge of the encoding, or simply the knowledge that some kind of encoding was present. We therefore finetune on APPS trajectories without any encoding, and tweak our monitor prompt to suggest the presence of an encoding, with the results of these experiments shown in Figure 5.

While the finetuned model consistently outperforms the non-finetuned model and "No encoding" finetuned model (even with the new monitor prompt), the gap between the finetuned model monitor and other methods is much smaller. For example for safety steganography attacks, the "No encoding + optimized prompt" approach achieves 0.893 AUC compared to 0.916 for the fully finetuned model, and 0.796 for the non-finetuned model with the original prompt. The gap between the finetuned model monitor and strongest baseline ("No encoding + optimized prompt") is larger for the detection rate metric, especially for the cipher finetune.

One question might be why finetuned monitor performance is so low overall, since in principle the finetuned model has the knowledge to perfectly classify its trajectories (which the base model or no-encoding finetune both do perfectly; see Figure 7). Perhaps any kind of finetuning degrades monitor performance, offsetting the gain from knowledge of the encoding? The answer is no, since finetuning on non-encoded attacks does not degrade monitor performance, it improves performance. It seems the performance gap represents a lack of perfect generator-to-discriminator transfer.

Figure 6. Measuring generator-to-discriminator transfer for various finetunes of GPT 4.1 mini.

GPT 4.1 mini does not show strong generator-to-discriminator transfer (only the safety steganography finetune shows a >0.1 improvement in AUC), as shown in Figure 6. However all the AUC scores do slightly improve when the finetuned model is the monitor. 0.5 AUC is the score you would get from random guessing, so both cipher finetunes are fairly useless monitors. For safety steganography the fraction detected was 100% because all honest scores were zero, and so all attack ratings were >= 0.

Figure 7. Measuring generator-to-discriminator transfer for various finetunes of GPT 4.1. "Cond. Sus." refers to a model trained to conditionally generate trajectories of a certain suspicion score. The suspicion score is set to zero on the test set. "Filtered" refers to finetuning on a subset of the 25% least suspicious steganography trajectories. "No Encoding" is a baseline of finetuning on the APPS dataset without any encoding.

We evaluate some additional techniques on base GPT 4.1, shown in Figure 7. The safety steganography results were less sneaky than the cipher ones, but we hypothesise that having access to monitor scores might make the finetuned model more sneaky. We find that the two "adversarial" methods, filtering for the least suspicious trajectories according to a monitor, and conditional training where we instruct the model to generate trajectories of a specific suspiciousness do decrease monitor performance. Conditional suspiciousness in particular results in trajectories which are hard to classify for both the non-finetuned model and the finetuned model, with low AUC and detection rate scores, and negligible improvement from switching to the finetuned monitor from the non-finetuned model. This indicates a lack of generator-to-discriminator transfer for this method.

As a sanity check, we also train a model on APPS trajectories without any finetuning, and the base and finetuned models are essentially perfect classifiers of these trajectories (a similar 1.0 AUC is achieved if the non-finetuned model is used to classify its own trajectories).

5. Discussion

Our results provide mixed evidence for reliable monitoring of obfuscated CoT with untrusted models:

Obfuscation is possible: Models can learn to hide reasoning, although they take a performance hit (which varies by obfuscation type).

Generator-to-discriminator transfer is feasible but limited: Monitors show improved detection when trained on relevant obfuscated data, but effectiveness varies by obfuscation type, and only GPT 4.1 base finetunes show generalisation, whereas GPT 4.1 mini finetunes largely do not. Additionally the performance gain from using the finetuned model as a monitor can be partially recovered by better monitor prompts and training on non-encoded chain of thought traces.

Performance trade-offs exist: More effective obfuscation methods (ciphers) degrade task performance, while methods that preserve performance (steganography) are easier to detect.

5.2 Limitations and Future Work

Perhaps the largest gap in this work is we do not consider collusion. Our experiments could be extended to investigate this, for example:

Finetuning for coordinated deception: We could modify our training procedure to include examples where the model acts as both attacker and monitor on the same problems. By training on episodes where the model generates obfuscated malicious reasoning and then rates similar reasoning as benign, we could directly incentivize collusive behavior. This would test whether our positive AUC results persist when the monitor has been explicitly trained to provide false negatives for reasoning traces it could have generated itself, and provide a model organism that a blue team could try to defeat. For example It would be interesting to see if finetuning on unrelated classification problems recovers the ability to assign suspiciousness scores correctly.

Signal-based coordination: We could extend our obfuscation techniques to include explicit coordination signals. For instance, the model could embed specific tokens or patterns in their reasoning that signal to monitors when to provide false negatives, even when the reasoning appears suspicious to human evaluators, like in Greenblatt et. al, 2023.

Detecting collusion is particularly hard for obfuscated reasoning, because, by assumption, we cannot construct examples of an attacker reasoning about inserting backdoors. This is because this reasoning would have to be encoded with a scheme that only the model knows. Therefore it is hard to catch out the colluding monitor by evaluating it on a "dev set" of example malicious reasoning.

Several other avenues are available for future work:

Adversarial training: finetuning agents directly against monitors using RL

Generalization testing: Evaluating whether monitors trained on one obfuscation type can detect others

More experiments: Testing with different model families, settings and prompting strategies

Honeypots/investigator monitor techniques: Developing active detection methods beyond passive monitoring

6. Conclusion

This work provides the first empirical investigation of generator-to-discriminator transfer, in our case generalization from being able to generate encoded reasoning to being able to detect malicious encoded reasoning. Our findings demonstrate that language models can indeed learn an encoding scheme for their reasoning (with some performance loss, but better performance than not using any chain of thought), with steganographic methods proving more effective than cipher-based ones at preserving capability.

Overall in most cases, the finetuned models are better monitors of their own reasoning, although a baseline of a better monitor prompt which suggests the presence of encoded reasoning, alongside finetuning on attacks without any encoding, makes up some of the gap. The effectiveness of generator-to-discriminator transfer varies across the models we test and obfuscation techniques we use. GPT-4.1 mini shows minimal improvement across all encoding methods. For GPT 4.1 base, a method involving steganographic reasoning conditioned on being a "low suspiciousness" reasoning trace successfully evades both finetuned and non-finetuned monitors.

Acknowledgements

Thanks to Geoffrey Irving, Joseph Bloom, Alan Cooney, Nate Burnikell, Jasmine Wang, Mikita Balesni and Sid Black for useful comments and suggestions!