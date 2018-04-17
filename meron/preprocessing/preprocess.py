import cv2
import dlib
import logging
import numpy as np
import pandas as pd
import os
import sys

from imutils.face_utils import shape_to_np
from imutils.face_utils import FaceAligner
from keras.engine import Model
from keras_vggface.vggface import VGGFace
from keras.preprocessing import image
from keras.applications.vgg16 import preprocess_input
from sklearn.decomposition import PCA


def ckfile(fname, logFlg=False, exit_flg=False):
    '''Check if a file exists'''

    if not os.path.isfile(fname):
        if logFlg:
            logFlg.error('Unable to find file: %s' % fname)

            return False

        if exit_flg:
            sys.exit()

    else:
        return True


class ImagePreProcess(object):
    '''Base class for pre-processing images MERON.

    ImagePreProcess hold functionality to pre-process images, such as detecting, aligning, and
    scaling facial imagery. In addition, extracting the convoluational features from the images.

    Derived classes contain database specific functionality for processing images.

    Parameters
    ----------
    landmark_file : Dlib trained facial landmark detection model. Used for aligning facial image
        C. Sagonas, E. Antonakos, G, Tzimiropoulos, S. Zafeiriou, M. Pantic.
        300 faces In-the-wild challenge: Database and results.
        Image and Vision Computing (IMAVIS), Special Issue on Facial Landmark Localisation "In-The-Wild". 2016.


    '''

    def __init__(self, landmark_file='./data/shape_predictor_68_face_landmarks.dat'):

        # ---------------
        # Initiate logger
        # ---------------
        self.logger = logging.getLogger("MERON_preprocess")
        self.logger.setLevel(logging.DEBUG)
        hdlr1 = logging.StreamHandler(stream=sys.stdout)
        fmt1 = logging.Formatter(
            "%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s"
        )
        hdlr1.setFormatter(fmt1)
        self.logger.addHandler(hdlr1)

        # --------------------------------------------
        # Initialize dlib's face detector (HOG-based)
        # Create the facial landmark predictor and the
        # face aligner
        # --------------------------------------------
        self.detector = dlib.get_frontal_face_detector()
        self.predictor = dlib.shape_predictor(landmark_file)
        self.fa = FaceAligner(self.predictor, desiredFaceWidth=224)

    def _detect_align(self, img, n_faces):
        '''Detect faces in image and align.

        Faces are detected from a single image using histogram of gradients (HOG)
        feature combined with a linear classifier, an image pyramid,
        and sliding window detection scheme.  The pose estimator was created by
        using dlib's implementation of the paper:
        One Millisecond Face Alignment with an Ensemble of Regression Trees by
        Vahid Kazemi and Josephine Sullivan, CVPR 2014
        and was trained on the iBUG 300-W face landmark dataset (see
        https://ibug.doc.ic.ac.uk/resources/facial-point-annotations/):
        C. Sagonas, E. Antonakos, G, Tzimiropoulos, S. Zafeiriou, M. Pantic.
        300 faces In-the-wild challenge: Database and results.
        Image and Vision Computing (IMAVIS), Special Issue on Facial Landmark Localisation
        "In-The-Wild". 2016.

        Aligns faces in canonical pose

        Parameters
        ----------

        img : cv2 image object
              RGB image object read by cv2 imread

        n_faces: integer
                 Maximium number of faces to detect in image


        Returns
        -------
        rtrn_img : A list of facial images that have been aligned  (rotation, scale, translation)
                   based on detected eye coordinates
        '''

        # Detect faces
        rects = self.detector(img, n_faces)

        rtrn_img = []
        for i, rect in enumerate(rects):
            # extract the ROI of the *original* face, then align the face
            # using facial landmarks
            aligned = self.fa.align(img, img, rect)
            rtrn_img.append(aligned)

        return rtrn_img

    def batch_image_detect_align(self, in_img_dir, out_img_dir, n_faces=1):
        '''Runs facial detection and alignment on a directory of images

        The method calls _detect_align for multiple images within a directory and writes processed
        images to output directory

        Parameters
        ----------
        in_img_dir : string
                     Directory of images to be processed (detected and aligned). Will try to process
                     all files in this directory
        out_img_dir : string
                      Directory to write processed images
        n_faces : integer
                  Max number of faces to detect in image (Currently only 1 face)
        '''

        for single_img in os.listdir(in_img_dir):
            if os.path.isfile(os.path.join(out_img_dir, single_img)):
                continue

            img = cv2.imread(os.path.join(in_img_dir, single_img))
            try:
                processed_img = self._detect_align(img, 1)  # n_faces

            # -----------------------------
            # Catch unsupported image types
            # No file writen for bad images
            # -----------------------------
            except RuntimeError:
                continue

            for i, proc_img in enumerate(processed_img):
                cv2.imwrite(os.path.join(out_img_dir, os.path.basename(single_img)), proc_img)

        return True

    def single_image_detect_align(self, img_file, n_faces=1):
        '''Runs facial detection and alignment on a single image

        Calls _detect_align for single image

        Parameters
        ----------
        img_file : string
                   File name of image
        n_faces : int
                  Max number of faces to detect in image

        Returns
        -------
        processed_img : A list of facial images that have been aligned  (rotation, scale, translation)
                   based on detected eye coordinates
        '''
        img = cv2.imread(img_file)
        processed_img = self._detect_align(img, n_faces)

        return processed_img


class MorphPreProcess(ImagePreProcess):
    '''Class sepecific to processing MORPH (Craniofacial Longitudinal Morphological Face
    Database)

    Derived class of ImagePreProcess
    '''

    def __init__(self, config_file='./config/config.json', dep='DEFAULT'):
        ImagePreProcess.__init__(self, config_file=config_file, dep=dep)

    def preprocess_morph_meta(self, morph_data_file, out_file):
        '''Contains MORPH database specific filters

        Parameters
        ----------
        morph_data_file : string
                          CSV file containing the meta data for each MORPH image
        out_file: string
                  CSV file of remainin MORPH images after specific filtering of meta data

        Returns
        -------
        data_morph : Pandas Dataframe
                     Dataframe of filtered MORPH image meta data
        '''

        data_morph = pd.read_csv(morph_data_file)

        # ------------------------------------
        # Calculate BMI from weight and height
        # ------------------------------------
        data_morph['bmi'] = data_morph['weight']*703/data_morph['height']**2

        # -----------
        # Filter data -- These are very specific to this dataset
        # -----------
        # Weight
        data_morph = data_morph.loc[(data_morph['weight'] < 450) & (data_morph['weight'] > 80)]

        # Height
        data_morph = data_morph.loc[(data_morph['height'] < 80) & (data_morph['height'] > 55)]

        # BMI
        data_morph.dropna(subset=['bmi'], inplace=True)
        data_morph = data_morph.loc[(data_morph['bmi'] < 50.) & (data_morph['bmi'] > 12.)]

        # Age
        data_morph = data_morph.loc[(data_morph['age'] <= 30)]

        # Facial hair
        data_morph = data_morph.loc[(data_morph['facial_hair'] != 1)]

        # Glasses
        data_morph = data_morph.loc[(data_morph['glasses'] != 1)]

        # ---------------------
        # Create BMI categories
        # ---------------------
        bins = [0, 18.5, 25, 30, 100]
        group_names = ['underweight', 'normal', 'overweight', 'obese']
        data_morph['bmi_cat'] = pd.cut(data_morph['bmi'], bins, labels=group_names)

        # --------------------
        # Categorical encoding
        # --------------------
        race_dummies = pd.get_dummies(data_morph['race'], prefix='race', drop_first=True)
        gender_dummies = pd.get_dummies(data_morph['gender'], prefix='gender', drop_first=True)
        bmi_dummies = pd.get_dummies(data_morph['bmi_cat'])
        data_morph = pd.concat([data_morph, race_dummies, gender_dummies, bmi_dummies], axis=1)

        # -------------------------
        # Remove "Album2/" in title
        # to match image names
        # -------------------------
        data_morph['photo'] = data_morph['photo'].str.replace(pat="Album2/", repl="")

        # ------------------------
        # Write processed data out
        # ------------------------
        data_morph.to_csv(out_file, index=False)

        return data_morph


class ExtractCNNfeatures(object):
    """Extract CNN features from images using fc6 of the VGG-Face convolutional neural network as
    a fixed feature extractor

    """

    def __init__(self):

        # ---------------
        # Initiate logger
        # ---------------
        self.logger = logging.getLogger("MERON_extractCNNfeatures")
        self.logger.setLevel(logging.DEBUG)
        hdlr1 = logging.StreamHandler(stream=sys.stdout)
        fmt1 = logging.Formatter(
            "%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s"
        )
        hdlr1.setFormatter(fmt1)
        self.logger.addHandler(hdlr1)

        self.extractor = None

    @staticmethod
    def chunks(lst, n):
        ''' Yield successive n-sized chunks from a list

        Parameters
        ----------
        lst : list
              Python list of items

        n : integer
            Number of items in the list to yield at a time
        '''

        for j, i in enumerate(range(0, len(lst), n)):
            yield (j, lst[i:i+n])

    def _prep_vgg_for_feature_extraction(self):
        '''Modify VGG model for producing facial features
           Oxford VGGFace Implementation using Keras Functional Framework v2+
                Very Deep Convolutional Networks for Large-Scale Image Recognition
                K. Simonyan, A. Zisserman
                arXiv:1409.1556

                https://github.com/rcmalli/keras-vggface

        Returns
        -------
        features_extractor : Keras Sequential Model
                             Modified version of the Oxford VGGFace model with the output layer and
                             first fully connected layer
        '''

        # Take second fully-connected layer as our output
        vgg_model = VGGFace()
        out = vgg_model.get_layer('fc6/relu').output
        self.extractor = Model(vgg_model.input, out)

        # Freeze all layers, since we're using as fixed feature extractor
        for layer in self.extractor.layers:
            layer.trainable = False

        # Fixed features so optimizer and loss functions are irrelavent
        self.extractor.compile(optimizer='Adam', loss='categorical_crossentropy')

        return self.extractor

    def _load_pp_images(self, img_dir, img_files):
        '''Load processed images for feature extraction
           Pre-process images which involves:
            -- Convert images from RGB to BGR
            -- Zero-center each color channel with respect to ImageNet dataset (no scaling)

            Images are first converted to numpy arrays.

        Parameters
        ----------
        img_dir : string
                  Directory to process images from

        img_files : string
                    List of image files (in img_dir) to be processed

        Returns
        -------
        images : Numpy array
                 Pre-processed image in the form of numpy array.
        '''

        images = []

        for i, single_img in enumerate(img_files):
            img = image.load_img(os.path.join(img_dir, single_img), target_size=(224, 224))
            arr = image.img_to_array(img)
            arr = np.expand_dims(arr, axis=0)

            if i == 0:
                images = arr
            else:
                images = np.concatenate((images, arr), axis=0)

        images = preprocess_input(images)

        return images

    def extract_batch(self, img_dir, processed_data_file, out_dir, n=1000):
        '''Batch extract VGG CNN features from a directory of images

        Parameters
        ----------
        img_dir : string
                  Directory of images to extract VGG features
        processed_data_file : string
                              CSV file with image meta data. Must contain column with filename of
                              photo. Column name must be: photo
        out_dir: string
                 Directory to write feature files
        n : integer
            Chunk size for number of images to pre-process at a time

        '''

        # Extract feature cnn from vgg
        self._prep_vgg_for_feature_extraction()

        # Read image meta data
        img_meta = pd.read_csv(processed_data_file)

        # Determine if image file exists
        img_meta['img_exists'] = img_meta.apply(
            lambda x, img_dir=img_dir: os.path.isfile(os.path.join(img_dir, x['photo'])), axis=1
        )
        img_meta = img_meta[img_meta['img_exists']]
        img_meta.drop(['img_exists'], axis=1, inplace=True)

        file_list = img_meta['photo']
        file_list = file_list.sample(frac=1)

        # Load image, pre-process, and extract features
        for i, img_files in self.chunks(file_list, n):
            X = self._load_pp_images(img_dir, img_files)

            # Extract convolutional features
            # VGG model expects input with 4 dimensions
            features = self.extractor.predict(X, verbose=1)
            img_files.reset_index(drop=True, inplace=True)
            df_fnames = pd.DataFrame(img_files, columns=['photo'])
            df = pd.DataFrame(features)
            df = df_fnames.join(df)

            # Write features to csv file for batch of n images
            fname = 'features_' + str(i) + '.csv'
            df.to_csv(os.path.join(out_dir, fname), index=False)