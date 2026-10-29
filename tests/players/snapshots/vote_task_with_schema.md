It is time to vote, Dave. The votes are secret until everyone has voted.

Vote for the one other player you think is the imposter. Use their exact name, one of: Alice, Bob, Charlie, Eve. You cannot vote for yourself. Also write your private reasoning about this vote, at most 60 words.

Your previous answer in this turn was rejected: "Zed" is not a player. Answer again and fix this.

Answer with only a JSON object that matches this JSON schema, without code fences or any other text:

{"properties": {"vote_for": {"description": "The exact name of the player you vote for.", "title": "Vote For", "type": "string"}, "private_reasoning": {"default": "", "description": "Your private reasoning, which nobody else sees.", "title": "Private Reasoning", "type": "string"}}, "required": ["vote_for"], "title": "VoteResponse", "type": "object"}
