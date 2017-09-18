from __future__ import (absolute_import, division, print_function)
from Muon import MaxEnt_model
from Muon import FFT_model
from Muon import ThreadModel
"""
 simple class to create a single object
 containing all of the models.
 Only need to pass a single object to all
 presenters
"""


class modelConstructor(object):

    def __init__(self,includeTransform):
        # construct transformation memebers
        if includeTransform:
            self.transformModels={}
            MaxEnt =MaxEnt_model.MaxEntModel()
            self.transformModels["MaxEnt"]=ThreadModel.ThreadModel(MaxEnt)
            FFT =FFT_model.FFTModel()
            self.transformModels[FFT.getName()]=ThreadModel.ThreadModel(FFT)

    def getModel(self,name):
        return self.transformModels[name]
