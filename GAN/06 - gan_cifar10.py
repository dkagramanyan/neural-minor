import matplotlib as mpl
mpl.use('Agg')

import pandas as pd
import numpy as np
import os
from keras.layers import Reshape, Flatten, LeakyReLU, Activation, Dense, BatchNormalization
from keras.layers.convolutional import Conv2D, UpSampling2D, MaxPooling2D, AveragePooling2D
from keras.regularizers import L1L2
from keras.models import Sequential
from keras.optimizers import Adam
from keras.callbacks import TensorBoard
from keras_adversarial.image_grid_callback import ImageGridCallback

from keras_adversarial import AdversarialModel, simple_gan, gan_targets
from keras_adversarial import AdversarialOptimizerSimultaneous, normal_latent_sampling
import keras.backend as K
from cifar10_utils import cifar10_data
from utils.image_utils import dim_ordering_unfix, dim_ordering_shape


def model_generator():
    model = Sequential()
    nch = 256
    reg = lambda: L1L2(l1=1e-7, l2=1e-7)
    h = 5
    model.add(Dense(nch * 4 * 4, input_dim=100, kernel_regularizer=reg()))
    model.add(BatchNormalization())
    model.add(Reshape(dim_ordering_shape((nch, 4, 4))))
    model.add(Conv2D(int(nch / 2), (h, h), padding='same', kernel_regularizer=reg()))
    model.add(BatchNormalization(axis=1))
    model.add(LeakyReLU(0.2))
    model.add(UpSampling2D(size=(2, 2)))
    model.add(Conv2D(int(nch / 2), (h, h), padding='same', kernel_regularizer=reg()))
    model.add(BatchNormalization(axis=1))
    model.add(LeakyReLU(0.2))
    model.add(UpSampling2D(size=(2, 2)))
    model.add(Conv2D(int(nch / 4), (h, h), padding='same', kernel_regularizer=reg()))
    model.add(BatchNormalization(axis=1))
    model.add(LeakyReLU(0.2))
    model.add(UpSampling2D(size=(2, 2)))
    model.add(Conv2D(3, (h, h), padding='same', kernel_regularizer=reg()))
    model.add(Activation('sigmoid'))
    return model


def model_discriminator():
    nch = 256
    h = 5
    reg = lambda: L1L2(l1=1e-7, l2=1e-7)

    c1 = Conv2D(int(nch / 4), (h, h), padding='same', kernel_regularizer=reg(),
                input_shape=(32, 32, 3))
    c2 = Conv2D(int(nch / 2), (h, h), padding='same', kernel_regularizer=reg())
    c3 = Conv2D(nch, (h, h), padding='same', kernel_regularizer=reg())
    c4 = Conv2D(1, (h, h), padding='same', kernel_regularizer=reg())

    model = Sequential()
    model.add(c1)
    model.add(MaxPooling2D(pool_size=(2, 2)))
    model.add(LeakyReLU(0.2))
    model.add(c2)
    model.add(MaxPooling2D(pool_size=(2, 2)))
    model.add(LeakyReLU(0.2))
    model.add(c3)
    model.add(MaxPooling2D(pool_size=(2, 2)))
    model.add(LeakyReLU(0.2))
    model.add(c4)
    model.add(AveragePooling2D(pool_size=(4, 4), padding='valid'))
    model.add(Flatten())
    model.add(Activation('sigmoid'))
    return model


def example_gan(adversarial_optimizer, path, opt_g, opt_d, nb_epoch, generator, discriminator, latent_dim,
                targets=gan_targets, loss='binary_crossentropy'):
    csvpath = os.path.join(path, "history.csv")
    if os.path.exists(csvpath):
        print("Already exists: {}".format(csvpath))
        return

    print("Training: {}".format(csvpath))

    generator.summary()
    discriminator.summary()
    gan = simple_gan(generator=generator,
                     discriminator=discriminator,
                     latent_sampling=normal_latent_sampling((latent_dim,)))

    model = AdversarialModel(base_model=gan,
                             player_params=[generator.trainable_weights, discriminator.trainable_weights],
                             player_names=["generator", "discriminator"])
    model.adversarial_compile(adversarial_optimizer=adversarial_optimizer,
                              player_optimizers=[opt_g, opt_d],
                              loss=loss)

    zsamples = np.random.normal(size=(10 * 10, latent_dim))

    def generator_sampler():
        xpred = dim_ordering_unfix(generator.predict(zsamples)).transpose((0, 2, 3, 1))
        return xpred.reshape((10, 10) + xpred.shape[1:])

    generator_cb = ImageGridCallback(os.path.join(path, "epoch-{:03d}.png"), generator_sampler, cmap=None)

    xtrain, xtest = cifar10_data()
    y = targets(xtrain.shape[0])
    ytest = targets(xtest.shape[0])
    callbacks = [generator_cb]
    if K.backend() == "tensorflow":
        callbacks.append(
            TensorBoard(log_dir=os.path.join(path, 'logs'), histogram_freq=0, write_graph=True, write_images=True))
    history = model.fit(x=xtrain, y=y, validation_data=(xtest, ytest),
                        callbacks=callbacks, nb_epoch=nb_epoch,
                        batch_size=32)

    df = pd.DataFrame(history.history)
    df.to_csv(csvpath)

    generator.save(os.path.join(path, "generator.h5"))
    discriminator.save(os.path.join(path, "discriminator.h5"))


def main():
    latent_dim = 100

    generator = model_generator()

    discriminator = model_discriminator()
    example_gan(AdversarialOptimizerSimultaneous(), "output/gan-cifar10",
                opt_g=Adam(1e-4, decay=1e-5),
                opt_d=Adam(1e-3, decay=1e-5),
                nb_epoch=100, generator=generator, discriminator=discriminator,
                latent_dim=latent_dim)

main()
