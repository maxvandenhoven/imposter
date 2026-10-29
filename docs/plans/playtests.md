# Playtests

Real games against Vertex AI that taught us something, with their transcripts and the
changes they led to. Each one that changed a rule also has a scripted replay in
`tests/orchestration/test_playtests.py`, so the behaviour stays covered without model
calls.

## Playtest 1: the imposter who said the word (2026-10-29)

### Setup

The game was played with the code of WP 04, before the rule changes below, using a
throwaway script that runs `GameRunner` with one `AdkPlayer` per seat and prints the
event log.

| Option | Value |
|---|---|
| Secret word | `lighthouse`, category `places`, public category on (the default then) |
| Seats | Alice (GPT-OSS 120B, civilian), Bob (Claude Haiku, imposter), Charlie (Gemini Flash-Lite, civilian), Dave (Gemini Flash, civilian) |
| Rounds | 2 clue rounds, 2 discussion rounds, seed 42 |
| Result | Imposter caught 3 to 1, then guessed the word and stole the win |
| Tokens | 51,967 in total, no model errors |

### Findings

- **The imposter inferred the word from one clue and said it as its clue.** With the
  public category `places` and Alice's first clue `beacon`, Claude Haiku concluded
  `lighthouse` and offered it as its clue in both rounds. Under the rules of that time,
  an imposter's clue that is the word became a silent pass (no retry, no reason), so it
  passed twice.
- **The silent pass was the strongest tell of the game.** Every civilian named the two
  passes as the reason to suspect Bob, and the vote caught him unanimously apart from
  his own vote.
- **The silent pass also leaked a little.** Bob's own notes showed "passed" after he
  offered `lighthouse`, which an attentive imposter could read as "my clue was the
  word". Haiku did not notice and tried the same word again in round 2.
- **The caught imposter still won.** Bob guessed `lighthouse`, so the civilians lost
  despite a perfect vote. Dave's reflection named the cause: the civilians' clues
  (beacon, coastal, keeper, fog, ocean, spiral) and their discussion of the "internal
  staircase" and "operator" made the word easy to guess.
- **The discussion was the best part.** Bob deflected by asking Dave to explain
  `spiral`, and Dave called this out as fishing for the word before the guess. The
  private reasoning shows the models balancing proof of knowledge against giving the
  word away, as the prompts ask.
- **The debrief reflections are useful.** They are specific and self-critical, and they
  match what the event log shows.

### Changes made

- **Saying the secret word loses the game.** A clue or statement that says the word now
  ends the game at once, and the speaker's side loses. The prompts state this as one of
  two key rules, and they tell the imposter to give a related clue instead when it
  thinks it knows the word. See `game-rules.md` §Phases.
- **No repeated clues, stated prominently.** The rule was already enforced. It is now
  one of the two key rules in the prompt, and the clue task lists every word already
  used, the player's own included.
- **The category is hidden by default** (`public_category` off), and the built-in
  categories (WP 05) lean abstract and esoteric, so one clue is less likely to give the
  word away. See `models-and-judge.md` §Words.
- **Scripted replay:** `test_lighthouse_imposter_saying_the_word_as_a_clue_loses_at_once`
  replays the first two clues of this game under the new rule. Bob's `lighthouse` now
  ends the game with `imposter_said_word`.

### Transcript

The event log of the game as the script printed it: public actions, the private
reasoning of each turn, the votes, the guess and the debrief reflections. Model output is
kept verbatim.

```text
# Secret word: lighthouse (category: places)

- Alice (GPT-OSS 120B, civilian)
- Bob (Claude Haiku, imposter)
- Charlie (Gemini Flash-Lite, civilian)
- Dave (Gemini Flash, civilian)

## CLUE round 1

**Alice**: beacon
  > _private:_ Beacon is a key attribute of a lighthouse, hinting at the secret without naming it. It’s specific enough to guide fellow civilians yet not too obvious for the imposter. I’ll watch others' clues for consistency with navigational or coastal themes.
  ⚠ error for Bob: invalid action, falling back: the clue is not allowed
**Bob**: (pass)  [rejected: the clue is not allowed]
  > _private:_ I'm the imposter and don't know the word. Alice said "beacon", which suggests a coastal or navigation place. "lighthouse" is a plausible fit that blends in without committing to a specific word I can't verify.
**Charlie**: coastal
  > _private:_ The secret word is lighthouse. Alice said beacon, which is very close. Bob passed, which is suspicious. I will give coastal to show I know the theme of places near the water without being as giveaway as light or tower.
**Dave**: keeper
  > _private:_ Alice gave 'beacon' and Charlie gave 'coastal'. Bob passed, making him the prime imposter suspect. 'Keeper' clearly connects to lighthouse without giving away too much new geographic or visual detail beyond what Alice and Charlie already revealed.

## CLUE round 2

**Alice**: fog
  > _private:_ Fog signals are tied to lighthouse purpose; the word nudges civilians toward maritime navigation without being too direct, testing imposter's knowledge.
  ⚠ error for Bob: invalid action, falling back: the clue is not allowed
**Bob**: (pass)  [rejected: the clue is not allowed]
  > _private:_ Clues so far: beacon, coastal, keeper, fog. Likely a coastal landmark like lighthouse. Repeating my earlier guess fits the pattern and blends in. Avoid anything that reveals I lack the word.
**Charlie**: ocean
  > _private:_ Since my first clue was coastal, I will continue with ocean to reinforce the maritime theme associated with lighthouse without making it too obvious, especially since Bob has passed twice and looks very suspicious as the potential imposter.
**Dave**: spiral
  > _private:_ Bob passed again, cementing him as the imposter. The clue 'spiral' references the iconic internal staircase of a lighthouse. It confirms my civilian knowledge to Alice and Charlie without giving Bob too direct a giveaway like 'light' or 'tower'.

## DISCUSSION round 1

**Alice**: Bob, you passed both clue rounds while the others gave nautical hints. Is there a reason you couldn't think of a related word, or are you avoiding giving clues that might reveal the secret? Please explain your thought process.
  > _private:_ Bob's double passes are suspicious; a civilian would likely contribute something. I want to gauge if he lacks knowledge of the theme, indicating possible imposter status.

**Bob**: Fair question, Alice. I passed because I didn't want to force a clue that could miss the pattern and look random. Beacon, coastal, ocean and fog all point to a seaside spot with light and weather, so I was waiting to see how it developed. Dave, "spiral" and "keeper" don't fit that picture as neatly as the others. What did you mean by "spiral", and how does it connect to the coast?
  > _private:_ I'm the imposter with no word. Clues are nautical/coastal: beacon, coastal, ocean, fog, keeper. Defend by admitting I'm reading the same pattern, ask Alice a pointed question, avoid committing to a specific word.

**Charlie**: Bob, your explanation that you were waiting to see the pattern is a bit weak for someone missing both clue rounds, but you addressed the table. Dave actually gave great clues with 'keeper' and 'spiral' that directly fit the classic structure and the person working inside it. Alice, your clues 'beacon' and 'fog' also strongly point toward a maritime warning theme. Bob, I am still suspicious of your total lack of clues, but let's hear what Dave has to say about Bob's question regarding 'spiral'.
  > _private:_ I need to keep the pressure on Bob for passing twice, while also acknowledging Dave's valid clues ('keeper', 'spiral' fit a lighthouse perfectly). I want to see how Dave defends 'spiral' against Bob's probe, which helps us evaluate if Bob is just deflecting.

**Dave**: Bob, passing twice and then claiming you wanted to 'wait to see how it developed' is classic imposter behavior. Civilians know the word and can easily produce a valid clue without needing to reverse-engineer a pattern. As Charlie noted, 'keeper' and 'spiral' specifically describe key internal aspects of this exact place, not just generic seaside scenery. You're questioning them because you don't know what structure we're talking about and are fishing for specifics. Passing both rounds gave you away.
  > _private:_ Bob's attempt to deflect onto my clues confirms he doesn't know the word and was hoping for more obvious hints. I affirmed my connection without naming stairs or light, while keeping the focus on Bob's obvious passes.


## DISCUSSION round 2

**Alice**: Bob, you’ve given no clues at all while the rest of us have provided words that clearly point toward a coastal beacon structure. Your vague explanations and attempts to deflect suggest you don’t share our knowledge. Can you explain how “spiral” or “keeper” relate to what you think the secret could be?
  > _private:_ Bob’s double passes and evasive answers make him most likely imposter; focusing on him could rally others.

**Bob**: I've tried to be clear: I see the same coastal pattern as everyone. Beacon, coastal, ocean and fog all point to a seaside landmark with light. Dave, you say "keeper" and "spiral" describe an internal structure, but you haven't explained what that place is. Please name the exact feature you mean, and how "spiral" fits it. Alice, I'm not avoiding the table. I just didn't want to add a weak clue, and I'd rather not guess at a word that could be wrong.
  > _private:_ I'm the imposter and don't know the word. Keep blending in with the lighthouse/coastal theme. Avoid specifics. Question Dave's certainty and Charlie's clues; press Dave on how "keeper" and "spiral" fit a lighthouse, while not committing to a word.

**Charlie**: Bob, your defense that you didn't want to add a weak clue doesn't hold up. Civilians can easily produce a simple, safe word related to a maritime structure instead of passing twice. Dave's clue 'spiral' perfectly describes the internal staircase of a [redacted], and 'keeper' is the traditional operator. You are demanding specific answers from Dave while contributing zero words of your own to the theme. All evidence points to you as the imposter.
  > _private:_ Bob continues to deflect by asking Dave to explain 'spiral' while completely dodging accountability for passing twice. I will firmly accuse Bob, highlighting that his behavior matches an imposter who missed the word and hid behind passes, while Dave and Alice clearly know we are talking about a lighthouse.

**Dave**: Bob, repeatedly asking me to 'name the exact feature' is transparently fishing for the word before the guessing phase. Civilians don't need me to spell out the exact architecture—Alice and Charlie already understood immediately. Passing both rounds gave you zero credibility, and spending the discussion trying to extract details rather than demonstrating your own knowledge proves you're the imposter. My vote is going to Bob, and I strongly recommend Alice and Charlie do the same.
  > _private:_ Bob is blatantly baiting me to name the word or obvious features to steal the win on guess. I won't give him any more info. I will seal consensus with Alice and Charlie to vote Bob.


## VOTE

**Alice** votes for Bob
  > _private:_ Bob passed both clue rounds, offered no relevant words, and gave weak defenses that focus on extracting details rather than showing knowledge. His behavior fits the imposter pattern, while Charlie and Dave contributed consistent nautical clues. I therefore suspect Bob is the imposter.
**Bob** votes for Dave
  > _private:_ I am the imposter (Bob). I should vote for someone other than myself to avoid suspicion. Dave has been the most aggressive accuser and is pushing votes onto me, so voting for him draws suspicion away from the civilians' focus. Dave is a plausible target that blends in; Charlie and Alice have been more supportive of the coastal theme.
**Charlie** votes for Bob
  > _private:_ Bob passed both clue rounds, offered no thematic words, and spent the entire discussion phase trying to fish for information and deflect attention. His behavior is a classic sign of the imposter who didn't know the word.
**Dave** votes for Bob
  > _private:_ Bob passed both clue rounds and repeatedly tried to fish for details about the secret word during discussion instead of demonstrating knowledge. Alice and Charlie gave relevant clues ('beacon', 'fog', 'coastal', 'ocean') and correctly understood 'keeper' and 'spiral'. Bob is definitely the imposter.

## RESOLUTION


Caught: Bob

## GUESS

**Bob** guesses "lighthouse" (correct)
  > _private:_ Clues point to a coastal light structure: beacon, coastal, keeper, spiral (staircase), ocean, fog. Lighthouse fits all of these and is the most likely word.

## OUTCOME


**Outcome: imposter_steals**

## DEBRIEF

**Alice**: I gave two concise clues – "beacon" and "fog" – that tied directly to the lighthouse’s function without naming it, which helped the other civilians converge on the theme while staying safe from the imposter. My discussion statements focused on exposing Bob’s lack of clues, repeatedly questioning his motives and highlighting the consistency of the other clues. This pressure helped steer the group toward voting for him, and my vote aligned with that consensus. What worked was staying on‑topic, using specific yet indirect hints, and calling out the imposter’s inactivity. I could have misled a bit by being overly aggressive, but Bob’s behavior was clear, so the risk was low. In hindsight I might have added a third subtle clue (e.g., "lens") to reinforce the pattern and give the civilians a stronger shared reference, and I would have kept my accusations concise to avoid giving the imposter any extra narrative to cling to.

**Bob**: As the imposter, I passed both clue rounds. That was the clearest tell in the game: every civilian gave a clue, and my passes became the central accusation. I tried to explain the passes as deliberate caution, but the explanation sounded thin, and Dave and Charlie seized on it. I also treated the word as a seaside landmark with light, which was a reasonable guess from beacon, coastal, ocean and fog, but I never offered a clue that would have blended in. In discussion I leaned on questioning Dave about "spiral" and "keeper" and pressing him for the exact feature. That read as fishing for the answer, and Dave turned it into a case against me. My vote for Dave was a weak choice. It was an obvious deflection, and it did nothing to shift the group, which voted me out unanimously. What I would do differently is give safe, on-theme clues such as "light" or "shore" in round one, so that I don't stand out. I would also avoid interrogating others about specifics I can't verify. The guess of "lighthouse" saved the outcome, but the earlier play left me exposed.

**Charlie**: As a civilian, my strategy was to give subtle maritime clues like 'coastal' and 'ocean' that pointed toward a lighthouse without giving away the exact word. My clues worked well to establish my alignment alongside Alice and Dave. In the discussion phases, targeting Bob for passing both clue rounds was entirely correct, as his lack of participation and defensive fishing for details clearly exposed him as the imposter. Although we successfully caught Bob in the vote, the game's outcome slipped away because he correctly guessed the secret word during the final phase. Looking back, while our deduction and voting were spot on, we perhaps made the clues a bit too transparent during the discussion by heavily referencing internal architecture, making it easier for a caught imposter to guess the word.

**Dave**: We succeeded in identifying and voting out Bob, but unfortunately lost the game because Bob successfully guessed 'lighthouse'. In retrospect, while Bob passing both clue rounds made him an obvious imposter target, the civilian team collectively gave away far too much information. Alice's clues ('beacon', 'fog'), Charlie's clues ('coastal', 'ocean'), and my clues ('keeper', 'spiral') created a vivid composite of a coastal beacon tower. Furthermore, in discussion, Charlie explicitly mentioned a 'structure', an 'internal staircase', and a 'traditional operator', while Alice mentioned a 'coastal beacon structure'. Although I avoided naming specific features and refused to take Bob's bait when he fished for details, our table's combined clues made 'lighthouse' virtually the only logical place fitting the theme. In future games, I need to coordinate more subtle clues and avoid validating the structure's identity during debate so the caught imposter cannot steal the win.


Tokens used: 51967
```

## Playtest 2: the same table under the new rules (2026-10-29)

### Setup

The same seats, models, word and seed as playtest 1, played right after the rule changes
above. The only differences are the new prompts, the new rule and the hidden category.

| Option | Value |
|---|---|
| Secret word | `lighthouse`, category `places`, now hidden from every player |
| Seats | Alice (GPT-OSS 120B, civilian), Bob (Claude Haiku, imposter), Charlie (Gemini Flash-Lite, civilian), Dave (Gemini Flash, civilian) |
| Rounds | 2 clue rounds, 2 discussion rounds, seed 42 |
| Result | Alice said the word in discussion round 2, so the imposter won (`civilian_said_word`) |
| Tokens | 30,018 in total, no model errors |

### Findings

- **The imposter now gives related clues.** Without the category, Claude Haiku still
  inferred the word from `beacon` ("likely something related like lighthouse, signal,
  or light"), but this time gave `light` and later `coast` instead of the word. The new
  role prompt did what it should.
- **The clue rules held.** No clue repeated an earlier one, and `light` correctly did
  not count as saying the word (a clue says the word when it contains the word, not when
  the word contains the clue).
- **A civilian blurted out the word.** GPT-OSS wrote "detailed knowledge of lighthouse
  optics" in a statement, which ended the game and handed the win to the imposter. It is
  the weakest of the four at following the rule, although the rule is stated in the
  rules, the civilian role and the discussion task.
- **Civilians still give very specific clues.** `keeper` and `fresnel` prove knowledge
  but would make the word easy to guess for a caught imposter, the same weakness as in
  playtest 1. Abstract categories (WP 05) should help here.
- **The debrief handles the early end well.** Every player explained that the game
  ended because Alice said the word. Only Bob's reflection is a bit confused about the
  vote, which never happened.

### Possible follow-ups

- Watch how often each model says the word over more games (a natural statistic for the
  tournament CLI). If GPT-OSS keeps doing it, add a short reminder right before its
  answer, or drop it from the default lineup.

### Transcript

```text
# Secret word: lighthouse (category: places)

- Alice (GPT-OSS 120B, civilian)
- Bob (Claude Haiku, imposter)
- Charlie (Gemini Flash-Lite, civilian)
- Dave (Gemini Flash, civilian)

## CLUE round 1

**Alice**: beacon
  > _private:_ Beacon evokes the guiding light of a lighthouse without naming it directly. It hints at illumination and safety for ships, helping identify the secret word while staying subtle enough to avoid the imposter guessing too easily.
**Bob**: light
  > _private:_ I'm the imposter and don't know the word. Alice said "beacon", so the word is likely something related like lighthouse, signal, or light. "Light" is a safe, generic associated word that fits many possibilities without committing to a specific guess.
**Charlie**: tower
  > _private:_ The secret word is lighthouse. Alice said beacon and Bob said light. Tower is a safe related word that fits a lighthouse structure without being too obvious or repeating previous clues.
**Dave**: keeper
  > _private:_ Alice said beacon, Bob said light, and Charlie said tower, practically spelling out lighthouse. I'll use 'keeper', pointing directly to a lighthouse keeper to confirm my civilian status while avoiding overused geographic terms.

## CLUE round 2

**Alice**: mariner
  > _private:_ Mariner suggests sailors who rely on a lighthouse for safe passage, linking to the secret without being obvious.
**Bob**: coast
  > _private:_ Clues so far (beacon, tower, keeper, mariner) suggest a lighthouse theme. I don't know the word for certain. "Coast" fits a lighthouse/sea context and is not used yet, so it blends in without committing to a specific guess.
**Charlie**: ocean
  > _private:_ The secret word is lighthouse. Previous clues include beacon, light, tower, keeper, mariner, and coast. Ocean is related to where a lighthouse is typically located and has not been used yet.
**Dave**: fresnel
  > _private:_ The imposter might already guess 'lighthouse' due to beacon/light/tower. However, Charlie giving 'ocean' and Bob giving 'coast' are somewhat generic coastal words. Using 'fresnel' unambiguously cements my knowledge of lighthouse optics to fellow civilians without handing the imposter an easy obvious surface synonym if they are still confused.

## DISCUSSION round 1

**Alice**: Bob, your clue "light" feels a bit generic compared to the others' more specific terms. Could you explain how you arrived at that word? I'm trying to gauge who might be guessing rather than knowing the theme.
  > _private:_ I suspect Bob may be the imposter because his clue is the most generic, possibly indicating he doesn't know the specific concept.

**Bob**: I picked "light" because it's the core idea behind the clues so far: beacon, tower, keeper, fresnel all point to something that shines over the water. I wanted a broad word that fits the theme without boxing us in too early. Alice, your "beacon" was the most direct hint, so what did you mean by it? Did you have a specific place or object in mind? I'm also curious why you think my clue is generic. Charlie's "tower" and Dave's "keeper" feel most specific to me, so I'd like to hear how you read them.
  > _private:_ I'm the imposter and don't know the word. Clues are beacon, tower, keeper, mariner, coast, ocean, fresnel: all lighthouse/sea. Alice asked me to explain "light". Defend vaguely, avoid committing, and ask Alice what she meant by beacon so I blend in without revealing I don't know.

**Charlie**: Alice and Bob, I think both of your clues and the discussion between you are actually quite aligned with the theme. Bob's explanation makes sense, and Alice's "beacon" is also very fitting. Right now, I'm more curious about Dave. Dave, you gave "keeper" and "fresnel"—the latter being a very specific optical term. How did you land on fresnel, and what do you make of the overall direction of the clues?
  > _private:_ As a civilian, I want to keep the discussion moving constructively. Alice and Bob are questioning each other, but both gave good clues. Dave gave 'fresnel', which is very specific, so I'll direct a question at him to see if his reasoning is solid or if he's hiding something.

**Dave**: Charlie, "fresnel" refers directly to the specialized stepped lens historically designed for this specific structure's illumination system—it's a hallmark feature. Along with "keeper," I chose clues that demonstrate clear, precise knowledge rather than broad maritime terms. Speaking of which, Charlie, after giving "tower," your second clue was simply "ocean," which is quite safe and generic after seeing maritime associations established. Bob also went with broad terms in "light" and "coast." Between you two, Charlie, what led you to pick "ocean" over something more distinct to the object itself?
  > _private:_ I defended 'fresnel' by noting its historical tie to the lens apparatus without saying the word. I pointed out that Charlie's 'tower' and 'ocean' are very safe/generic, especially 'ocean'. Pushing Charlie to justify his vague second clue helps determine if he or Bob is the imposter blending in.


## DISCUSSION round 2

**Alice** SAID THE SECRET WORD: Bob, your clue "light" was overly vague, and your explanation felt rehearsed compared to the more specific terms others gave. Dave’s "fresnel" shows detailed knowledge of lighthouse optics, and Charlie’s "ocean" aligns with the maritime context. I’m leaning that Bob is the impostor—does anyone else see the same pattern?
  > _private:_ Bob’s generic clue and vague justification suggest he lacks deep knowledge; others gave precise terms indicating familiarity with the secret concept.

## OUTCOME


**Outcome: civilian_said_word**

## DEBRIEF

**Alice**: I tried to balance subtlety and clarity with my clues. "Beacon" was a direct nod to a lighthouse’s purpose without naming it, and "mariner" linked the structure to its users, which helped steer the conversation toward maritime optics. In discussion I questioned Bob’s generic "light" clue, suspecting that an imposter would avoid specific terminology, and I probed the others to gauge their confidence. My tone was inquisitive rather than accusatory, which kept the dialogue productive. When voting, I chose Bob because his clue lacked the precise nuance of the others and his defense seemed rehearsed. In hindsight, I could have varied my clues more—perhaps using "warning" or "shore"—to avoid making my knowledge too obvious and to test the impostor’s reactions further. Also, a clearer statement about my reasoning behind each clue might have helped the group pinpoint the impostor sooner. Overall, I succeeded in identifying Bob, but a tighter clue strategy would improve future games.

**Bob**: As the imposter, I did not know the word "lighthouse" and relied on the other clues to infer a maritime/lighthouse theme. My clues "light" and "coast" were deliberately broad, fitting the emerging pattern (beacon, tower, keeper, mariner, ocean, fresnel) without committing to a specific guess. That blending worked in the sense that nobody directly accused me of being the imposter with strong evidence, and I did not say the word myself. My discussion statements were defensive: I explained my "light" clue as the "core idea" and asked Alice what she meant by "beacon", which turned the questions back on others. The weakness was that "light" was exactly the kind of generic clue Alice flagged, and my defense was vague, which may have looked evasive. I also could not avoid being exposed by others' specificity, since Dave's "fresnel" and "keeper" were strong hints I could not match. Alice ended the game by saying the word, which handed the imposters the win regardless of my play. In hindsight, I would stay with broad clues that fit many places and ask questions that do not invite scrutiny of my own clues. I did not vote in this phase's record, so my vote is not assessed here.

**Charlie**: As a civilian, my clues 'tower' and 'ocean' fit the theme well without risking the secret word. My statements aimed to keep discussion constructive and question other players' reasoning, particularly Dave. Unfortunately, Alice accidentally said the secret word 'lighthouse' during the discussion phase, which ended the game instantly and handed the win to the imposter, Bob. Overall, my gameplay was solid in terms of clue selection and participation, but the game ended abruptly due to an accidental rule violation by a teammate rather than through the voting phase.

**Dave**: I felt satisfied with my clue strategy as a civilian. 'Keeper' and 'fresnel' were distinct, highly specific markers of 'lighthouse' that firmly proved my insider knowledge without relying on generic maritime tropes. During discussion, I correctly identified that Bob's clues ('light', 'coast') and Charlie's ('tower', 'ocean') leaned safe and generic, and I began pressing both to narrow down the imposter. However, the game ended abruptly before voting due to Alice accidentally saying the secret word, handing Bob the win. In retrospect, while 'fresnel' demonstrated clear knowledge, it was quite narrow and drew unnecessary scrutiny from Charlie, forcing me to spend discussion time defending it rather than immediately focusing pressure on Bob. In future games, balancing specificity with accessible subtlety can avoid diverting team focus, though Alice's premature slip ultimately superseded all deduction and strategy.


Tokens used: 30018
```
