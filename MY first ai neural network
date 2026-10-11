import torch
import torch.nn as nn
import torch.nn.functional as F

# 1. the text lives right here in the code (change it to anything you like)
text = """
the cat sat on the mat. the dog sat on the log.
the cat saw the dog. the dog saw the cat.
the sun is up. the moon is down. the day is long.
a bird can fly. a fish can swim. a cat can jump.
the sky is blue. the grass is green. the sun is hot.
"""

chars = sorted(set(text))
stoi = {c: i for i, c in enumerate(chars)}
itos = {i: c for c, i in stoi.items()}
data = torch.tensor([stoi[c] for c in text])

x = data[:-1]   # current letters
y = data[1:]    # the letters that actually came next

# 2. the model: a table of numbers that can be adjusted
class Net(nn.Module):
    def __init__(self, vocab):
        super().__init__()
        self.table = nn.Embedding(vocab, vocab)

    def forward(self, x):
        return self.table(x)   # a score for every possible next letter

model = Net(len(chars))
opt = torch.optim.AdamW(model.parameters(), lr=0.01)

# 3. training: guess, measure the mistake, adjust
for step in range(2000):
    ix = torch.randint(len(x), (64,))          # pick 64 random spots in the text
    logits = model(x[ix])                      # the model's guesses
    loss = F.cross_entropy(logits, y[ix])      # how wrong were they?
    opt.zero_grad()
    loss.backward()                            # work out how to improve
    opt.step()                                 # make the adjustment
    if step % 200 == 0:
        print(step, loss.item())

# 4. generate text
cur = 0
out = [itos[cur]]
for _ in range(300):
    probs = F.softmax(model(torch.tensor([cur]))[0], dim=-1)
    cur = torch.multinomial(probs, 1).item()
    out.append(itos[cur])
print("".join(out))
