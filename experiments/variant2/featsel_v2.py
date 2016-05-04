from __future__ import print_function
import argparse
import time
import os

import lasagne
from lasagne.layers import DenseLayer, InputLayer
from lasagne.nonlinearities import sigmoid, softmax  # , tanh, linear
import numpy as np
import theano
import theano.tensor as T


def iterate_minibatches(inputs, targets, batchsize, axis=0, shuffle=False):
    assert len(inputs) == len(targets)
    assert axis >= 0 and axis < len(inputs.shape)
    targets = targets.transpose()

    if axis == 1:
        inputs = inputs.transpose()

    if shuffle:
        indices = np.arange(len(inputs))
        np.random.shuffle(indices)

    for start_idx in range(0, len(inputs) - batchsize + 1, batchsize):
        if shuffle:
            excerpt = indices[start_idx:start_idx + batchsize]
        else:
            excerpt = slice(start_idx, start_idx + batchsize)

        if axis == 0:
            yield inputs[excerpt].transpose(), targets[excerpt]
        elif axis == 1:
            yield inputs[excerpt], targets


def onehot_labels(labels, min_val, max_val):
    output = np.zeros((len(labels), max_val - min_val + 1), dtype="int32")
    output[np.arange(len(labels)), labels - min_val] = 1
    return output


def generate_test_predictions(minibatches, pred_fn):

    # Obtain the predictions over all the examples
    all_predictions = np.zeros((0), "int32")
    all_probabilities = np.zeros((0), "float32")
    for batch in minibatches:
        inputs, _ = batch

        probs = pred_fn(inputs)
        all_probabilities = np.concatenate((all_probabilities, probs[:, 1]),
                                           axis=0)

        predictions = probs.argmax(axis=1)
        all_predictions = np.concatenate((all_predictions, predictions),
                                         axis=0)

    # Write the predictions to a text file
    filename_pred = "test_preds_" + time.strftime("%Y-%M-%d_%T") + ".txt"
    with open(filename_pred, "w") as f:
        f.write(",".join([str(p) for p in all_predictions]))

    # Also write the probabilities of the positive class to a text file
    filename_prob = "test_probs_" + time.strftime("%Y-%M-%d_%T") + ".txt"
    with open(filename_prob, "w") as f:
        f.write(",".join([str(p) for p in all_probabilities])  )


def monitoring(minibatches, dataset_name, val_fn, monitoring_labels,
               pred_fn=None, n_classes=2):

    monitoring_values = np.zeros(len(monitoring_labels), dtype="float32")
    all_probs = np.zeros((0, n_classes), "float32")
    all_targets = np.zeros((0), "float32")
    global_batches = 0

    for batch in minibatches:
        inputs, targets = batch

        # Update monitored values
        out = val_fn(inputs, targets)
        monitoring_values = monitoring_values + out
        global_batches += 1

        # Update the prediction / target lists
        if pred_fn is not None:
            probs = pred_fn(inputs)
            all_probs = np.concatenate((all_probs, probs), axis=0)
            all_targets = np.concatenate((all_targets, targets), axis=0)

    # Print monitored values
    monitoring_values /= global_batches
    for (label, val) in zip(monitoring_labels, monitoring_values):
        print ("  {} {}:\t\t{:.6f}".format(dataset_name, label, val))

    # Print supervised-specific metrics
    if pred_fn is not None:
        # Compute the confusion matrix
        all_predictions = all_probs.argmax(1)
        confusion = np.zeros((n_classes, n_classes))
        for i in range(len(all_predictions)):
            confusion[all_targets[i], all_predictions[i]] += 1

        # Print the BER (balanced error rate)
        ber = 0.5 * (confusion[0, 1] / confusion.sum(axis=1)[0] +
                     confusion[1, 0] / confusion.sum(axis=1)[1])
        print ("  {} ber:\t\t\t{:.6f}".format(dataset_name, ber))

        # Compute and print the AUC (this implementation is inefficient but
        # simple, it may be sped up if it ever becomes a bottleneck. It comes
        # from http://www.cs.ru.nl/~tomh/onderwijs/dm/dm_files/roc_auc.pdf)
        preds_for_neg_examples = all_predictions[np.argwhere(all_targets == 0)]
        preds_for_pos_examples = all_predictions[np.argwhere(all_targets == 1)]
        auc = 0.
        for neg_pred in preds_for_neg_examples:
            for pos_pred in preds_for_pos_examples:
                if pos_pred > neg_pred:
                    auc += 1.
        auc /= (len(preds_for_neg_examples) * len(preds_for_pos_examples))
        print ("  {} auc:\t\t\t{:.6f}".format(dataset_name, auc))
        return auc

# Main program
def execute(training, dataset, n_output, embedding_source, num_epochs=500):
    # Load the dataset
    print("Loading data")
    if dataset == 'genomics':
        from feature_selection.experiments.common.dorothea import load_data
        x_train, y_train = load_data('train', 'standard', False, 'numpy')
        x_valid, y_valid = load_data('valid', 'standard', False, 'numpy')

        # WARNING : The dorothea dataset has no test labels
        x_test = load_data('test', 'standard', False, 'numpy')
        y_test = None
        
    elif dataset == 'genomics_all':
        from feature_selection.experiments.common.dorothea import load_data
        x_train, y_train = load_data('all', 'standard', False, 'numpy')
        x_valid = None
        y_valid = None
        x_test = None
        y_test = None

    elif dataset == 'debug':
        x_train = np.random.rand(10, 100).astype(np.float32)
        x_valid = np.random.rand(2, 100).astype(np.float32)
        x_test = np.random.rand(2, 100).astype(np.float32)
        y_train = np.random.randint(0, 2, size=10).astype('int32')
        y_valid = np.random.randint(0, 2, size=2).astype('int32')
        y_test = np.random.randint(0, 2, size=2).astype('int32')

    else:
        print("Unknown dataset")
        return

    n_samples, n_feats = x_train.shape
    n_classes = y_train.max() + 1
    n_batch = 100 # ALERT
    save_path = '/data/lisatmp4/carriepl/FeatureSelection/'

    # Prepare Theano variables for inputs and targets
    input_var = T.matrix('inputs')
    target_var = T.ivector('targets')
    lr = theano.shared(np.float32(1e-3), 'learning_rate')

    # Build model
    print("Building model")

    if embedding_source == "predicted":
        encoder_net = InputLayer((n_batch, n_samples), input_var)
        encoder_net = DenseLayer(encoder_net, num_units=n_output)
        encoder_net = DenseLayer(encoder_net, num_units=n_output)
        feat_emb = lasagne.layers.get_output(encoder_net)
    else:
        feat_emb_val = np.load(save_path + embedding_source).items()[0][1]
        feat_emb = theano.shared(feat_emb_val, 'feat_emb')
        encoder_net = InputLayer((n_batch, n_output), feat_emb.get_value())

    decoder_net = DenseLayer(encoder_net, num_units=n_samples,
                             nonlinearity=sigmoid)

    discrim_net = InputLayer((n_batch, n_feats), input_var.transpose())
    discrim_net = DenseLayer(discrim_net, num_units=n_output, W=feat_emb)
    discrim_net = DenseLayer(discrim_net, num_units=n_output*2) # ALERT
    discrim_net = DenseLayer(discrim_net, num_units=n_classes,
                             nonlinearity=softmax)

    # Create a loss expression for training
    print("Building and compiling training functions")

    # Expressions required for training
    if training == "supervised":
        prediction = lasagne.layers.get_output(discrim_net)
        #loss = lasagne.objectives.categorical_crossentropy(prediction,
        #                                                   target_var).mean()
        losses = lasagne.objectives.categorical_crossentropy(prediction, target_var)
        weighted_losses = (0.3 * losses * T.eq(target_var, 0) + 
                           3.0 * losses * T.eq(target_var, 1)).astype("float32") # ALERT
        loss = weighted_losses.mean()
        params = lasagne.layers.get_all_params(discrim_net, trainable=True)
    elif training == "unsupervised":
        reconstruction = lasagne.layers.get_output(decoder_net)
        loss = lasagne.objectives.binary_crossentropy(reconstruction,
                                                      input_var).mean()
        params = lasagne.layers.get_all_params(decoder_net, trainable=True)

    updates = lasagne.updates.rmsprop(loss,
                                      params,
                                      learning_rate=lr)
    # updates = lasagne.updates.sgd(loss,
    #                              params,
    #                              learning_rate=lr)
    # updates = lasagne.updates.momentum(loss, params,
    #                                    learning_rate=lr, momentum=0.0)
    updates[lr] = (lr * 0.99).astype("float32")
    updates[feat_emb] = feat_emb ###### WARNING ALERT

    # Compile a function performing a training step on a mini-batch (by
    # giving the updates dictionary) and returning the corresponding
    # training loss.
    # Warnings about unused inputs are ignored because otherwise Theano might
    # complain about the targets being a useless input when doing unsupervised
    # training of the network.
    train_fn = theano.function([input_var, target_var], loss,
                               updates=updates,
                               on_unused_input='ignore')

    # Expressions required for test
    if training == "supervised":
        test_prediction = lasagne.layers.get_output(discrim_net,
                                                    deterministic=True)
        test_predictions_loss = lasagne.objectives.categorical_crossentropy(
            test_prediction, target_var).mean()
        test_class = T.argmax(test_prediction, axis=1)
        test_acc = T.mean(T.eq(T.argmax(test_prediction, axis=1), target_var),
                          dtype=theano.config.floatX) * 100.

        val_fn = theano.function([input_var, target_var],
                                 [test_predictions_loss, test_acc])
        pred_fn = theano.function([input_var], test_prediction)
        monitor_labels = ["pred. loss", "accuracy"]
    elif training == "unsupervised":
        test_reconstruction = lasagne.layers.get_output(decoder_net,
                                                        deterministic=True)
        test_reconstruction_loss = lasagne.objectives.binary_crossentropy(
            test_reconstruction, input_var).mean()

        val_fn = theano.function([input_var, target_var],
                                 [test_reconstruction_loss],
                                 on_unused_input='ignore')
        pred_fn = None
        monitor_labels = ["recon. loss"]

    # Finally, launch the training loop.
    print("Starting training...")
    # We iterate over epochs:
    best_valid_auc = 0.0
    minibatch_axis = int(training == "unsupervised")
    for epoch in range(num_epochs):
        # In each epoch, we do a full pass over the training data to updates
        # the parameters:
        start_time = time.time()
        for batch in iterate_minibatches(x_train, y_train, n_batch,
                                         minibatch_axis, shuffle=True):
            inputs, targets = batch
            train_fn(inputs, targets)

        # Monitor progress
        print("Epoch {} of {}".format(epoch + 1, num_epochs))

        train_minibatches = iterate_minibatches(x_train, y_train, n_batch,
                                                minibatch_axis, shuffle=False)
        monitoring(train_minibatches, "train", val_fn,
                   monitor_labels, pred_fn, n_classes)

        # Only monitor on the validation set if training in a supervised way
        # otherwise the dimensions will not match.
        if training == "supervised":
            valid_minibatches = iterate_minibatches(x_valid, y_valid, n_batch,
                                                    minibatch_axis,
                                                    shuffle=False)
            valid_auc = monitoring(valid_minibatches, "valid", val_fn,
                                   monitor_labels, pred_fn, n_classes)

            if valid_auc > best_valid_auc:
                best_valid_auc = valid_auc
                
                # If there are test labels, perform the monitoring. Else, print
                # the test predictions for external evaluation.
                if y_test is None:
                    test_minibatches = iterate_minibatches(x_test, x_test,
                                                           n_batch,
                                                           minibatch_axis,
                                                           shuffle=False)
                    generate_test_predictions(test_minibatches, pred_fn)
                else:
                    test_minibatches = iterate_minibatches(x_test, y_test,
                                                           n_batch,
                                                           minibatch_axis,
                                                           shuffle=False)
                    monitoring(test_minibatches, "test", val_fn,
                               monitor_labels, pred_fn, n_classes)


                # Save network weights to a file
                if not os.path.exists(save_path):
                    os.makedirs(save_path)

                #np.savez(save_path+'model1.npz',
                #         *lasagne.layers.get_all_param_values(decoder_net))
                #np.savez(save_path+'model2.npz',
                #         *lasagne.layers.get_all_param_values(discrim_net))
                
        print("  total time:\t\t\t{:.3f}s".format(time.time() - start_time))


    # Save the learnt embedding (over the training set) to a file
    if training == "unsupervised":
        # Define a function serving only to compute the feature embedding over
        # some data
        emb_fn = theano.function([input_var], feat_emb)

        # Compute the embedding over all the training data and save the result
        np.savez(save_path + "embedding_%i.npz" % n_output,
                 emb_fn(x_train.transpose()))


def main():
    parser = argparse.ArgumentParser(description="""Implementation of the
                                     feature selection v2""")
    parser.add_argument('training',
                        default='supervised',
                        help='Type of training.')
    parser.add_argument('dataset',
                        default='debug',
                        help='Dataset.')
    parser.add_argument('n_output',
                        default=100,
                        help='Output dimension.')
    parser.add_argument('embedding_source',
                        default="predicted",
                        help='Source for the feature embedding. Either' +
                             '"predicted" or the name of a file from which' +
                             'to load a learned embedding')
    parser.add_argument('--num_epochs',
                        '-ne',
                        type=int,
                        default=5,
                        help="""Optional. Int to indicate the max'
                        'number of epochs.""")

    args = parser.parse_args()

    execute(args.training, args.dataset, int(args.n_output),
            args.embedding_source, int(args.num_epochs))


if __name__ == '__main__':
    main()
