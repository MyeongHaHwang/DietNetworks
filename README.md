# TODO list

**Proof of concept:**
- [ ] Generate bigram/trigram IMDB dataset
- [ ] Train IMDB with weight-auxiliary-model concatenating uni/bi/tri grams to increase data dimensionality.
- [ ] Train IMDB regular-AE MLP concatenating uni/bi/tri grams to increase data dimensionality (2 versions supervised & semi-supervised).
- [x] Train the model using partially labeled subsets (10%, 25%, 50% ...): the model does not seem to suffer from using few labeled samples.

What we would like to see: regular-AE MLP overfits whereas weight-aux-model does not.

**IMBD comparison:**
- [ ] Run experiments on https://github.com/mesnilgr/nbsvm using uni/bi/tri grams.
- [ ] Run experiments on https://github.com/libofang/DV-ngram using uni/bi/tri grams.
- [ ] Run experiments on https://github.com/mesnilgr/iclr15 using uni/bi/tri grams.

**1000 genomes:**
- [x] Wrap dataset
- [ ] Run experiments
- [ ] Run PCA/k-means baselines

# Results

**Partially labeled subsets on IMDB:**

|Model|Partial subset|Acc.|
|-----|--------------|----|
|Ours|100%||
|Ours|50%||
|Ours|25%||
|Ours|10%||
|Ours|1%||

**SOTA methods on IMDB:**



**100 Genomes:**

|Model|Acc.|
|-----|----|
|Ours||

# Feature-Selection
Ackwnoledgement: we used scikit feature (added to the repo) for some of our baselines.
https://github.com/jundongl
