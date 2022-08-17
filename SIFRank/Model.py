# -*- coding: utf-8 -*-
"""sifrank.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1vV6MwDXMHO4ipttA4xjvMjmHTep9cw3k
"""

# https://github.com/sunyilgdx/SIFRank
# https://medium.com/@aayanthi/bert-as-service-with-google-colab-e235472e108d

from google.colab import drive
drive.mount('/content/gdrive')

pip install embeddings

import nltk
nltk.download('stopwords')

#! /usr/bin/env python
# -*- coding: utf-8 -*-
# __author__ = "Sponge"
# Date: 2019/6/19
import numpy
import torch
import nltk
from nltk.corpus import stopwords
english_punctuations = [',', '.', ':', ';', '?', '(', ')', '[', ']', '&', '!', '*', '@', '#', '$', '%']
stop_words = set(stopwords.words("english"))
wnl=nltk.WordNetLemmatizer()
considered_tags = {'NN', 'NNS', 'NNP', 'NNPS', 'JJ','VBG'}

class SentEmbeddings():

    def __init__(self,
                 word_embeddor,
                 weightfile_pretrain='/content/gdrive/My Drive/enwiki_vocab_min200.txt',
                 weightfile_finetune='../auxiliary_data/inspec_vocab.txt',
                 weightpara_pretrain=2.7e-4,
                 weightpara_finetune=2.7e-4,
                 lamda=1.0,database="",embeddings_type="elmo"):

        if(database=="Inspec"):
            weightfile_finetune = '../auxiliary_data/inspec_vocab.txt'
        elif(database=="Duc2001"):
            weightfile_finetune = '../auxiliary_data/duc2001_vocab.txt'
        elif(database=="SemEval2017"):
            weightfile_finetune = '../auxiliary_data/semeval_vocab.txt'
        else:
            weightfile_finetune = '/content/gdrive/My Drive/enwiki_vocab_min200.txt'

        self.word2weight_pretrain = get_word_weight(weightfile_pretrain, weightpara_pretrain)
        self.word2weight_finetune = get_word_weight(weightfile_finetune, weightpara_finetune)
        self.word_embeddor = word_embeddor
        self.lamda=lamda
        self.database=database
        self.embeddings_type=embeddings_type

    def get_tokenized_sent_embeddings(self, text_obj, if_DS=False, if_EA=False):
        """
        Based on part of speech return a list of candidate phrases
        :param text_obj: Input text Representation see @InputTextObj
        :param if_DS: if take document segmentation(DS)
        :param if_EA: if take  embeddings alignment(EA)
        """
        # choose the type of word embeddings:elmo or elmo_transformer or glove
        if(self.embeddings_type=="elmo" and if_DS==False):
            elmo_embeddings, elmo_mask = self.word_embeddor.get_tokenized_words_embeddings([text_obj.tokens])
        elif(self.embeddings_type=="elmo" and if_DS==True and if_EA==False):
            tokens_segmented = get_sent_segmented(text_obj.tokens)
            elmo_embeddings, elmo_mask = self.word_embeddor.get_tokenized_words_embeddings(tokens_segmented)
            elmo_embeddings = splice_embeddings(elmo_embeddings,tokens_segmented)
        elif (self.embeddings_type == "elmo" and if_DS == True and if_EA == True):
            tokens_segmented = get_sent_segmented(text_obj.tokens)
            elmo_embeddings, elmo_mask = self.word_embeddor.get_tokenized_words_embeddings(tokens_segmented)
            elmo_embeddings = context_embeddings_alignment(elmo_embeddings, tokens_segmented)
            elmo_embeddings = splice_embeddings(elmo_embeddings, tokens_segmented)

        # elif(self.embeddings_type=="elmo_transformer"):
        #     elmo_embeddings= self.word_embeddor.get_tokenized_words_embeddings([text_obj.tokens])
        # elif (self.embeddings_type == "glove"):
        #     elmo_embeddings = self.word_embeddor.get_tokenized_words_embeddings([text_obj.tokens])

        else:
            elmo_embeddings, elmo_mask = self.word_embeddor.get_tokenized_words_embeddings(text_obj.tokens)

        candidate_embeddings_list=[]

        weight_list = get_weight_list(self.word2weight_pretrain, self.word2weight_finetune, text_obj.tokens, lamda=self.lamda, database=self.database)

        sent_embeddings = get_weighted_average(text_obj.tokens, text_obj.tokens_tagged, weight_list, elmo_embeddings[0], embeddings_type=self.embeddings_type)

        for kc in text_obj.keyphrase_candidate:
            start = kc[1][0]
            end = kc[1][1]
            kc_emb = get_candidate_weighted_average(text_obj.tokens, weight_list, elmo_embeddings[0], start, end,
                                                    embeddings_type=self.embeddings_type)
            candidate_embeddings_list.append(kc_emb)

        return sent_embeddings,candidate_embeddings_list

def context_embeddings_alignment(elmo_embeddings, tokens_segmented):

    """
    Embeddings Alignment
    :param elmo_embeddings: The embeddings from elmo
    :param tokens_segmented: The list of tokens list
     <class 'list'>: [['Twenty', 'years', ...,'practices', '.'],['The', 'out-of-print',..., 'libraries']]
    :return:
    """
    token_emb_map = {}
    n = 0
    for i in range(0, len(tokens_segmented)):

        for j, token in enumerate(tokens_segmented[i]):

            emb = elmo_embeddings[i, 1, j, :]
            if token not in token_emb_map:
                token_emb_map[token] = [emb]
            else:
                token_emb_map[token].append(emb)
            n += 1

    anchor_emb_map = {}
    for token, emb_list in token_emb_map.items():
        average_emb = emb_list[0]
        for j in range(1, len(emb_list)):
            average_emb += emb_list[j]
        average_emb /= float(len(emb_list))
        anchor_emb_map[token] = average_emb

    for i in range(0, elmo_embeddings.shape[0]):
        for j, token in enumerate(tokens_segmented[i]):
            emb = anchor_emb_map[token]
            elmo_embeddings[i, 2, j, :] = emb

    return elmo_embeddings

def mat_division(vector_a, vector_b):
    a = vector_a.detach().numpy()
    b = vector_b.detach().numpy()
    A = numpy.mat(a)
    B = numpy.mat(b)
    # if numpy.linalg.det(B) == 0:
    #     print("This matrix is singular, cannot be inversed!")
    #     return
    return torch.from_numpy(numpy.dot(A.I,B))

def get_sent_segmented(tokens):
    min_seq_len = 16
    sents_sectioned = []
    if (len(tokens) <= min_seq_len):
        sents_sectioned.append(tokens)
    else:
        position = 0
        for i, token in enumerate(tokens):
            if (token == '.'):
                if (i - position >= min_seq_len):
                    sents_sectioned.append(tokens[position:i + 1])
                    position = i + 1
        if (len(tokens[position:]) > 0):
            sents_sectioned.append(tokens[position:])

    return sents_sectioned

def splice_embeddings(elmo_embeddings,tokens_segmented):
    new_elmo_embeddings = elmo_embeddings[0:1, :, 0:len(tokens_segmented[0]), :]
    for i in range(1, len(tokens_segmented)):
        emb = elmo_embeddings[i:i + 1, :, 0:len(tokens_segmented[i]), :]
        new_elmo_embeddings = torch.cat((new_elmo_embeddings, emb), 2)
    return new_elmo_embeddings

def get_effective_words_num(tokened_sents):
    i=0
    for token in tokened_sents:
        if(token not in english_punctuations):
            i+=1
    return i

def get_weighted_average(tokenized_sents, sents_tokened_tagged,weight_list, embeddings_list, embeddings_type="elmo"):
    # weight_list=get_normalized_weight(weight_list)
    assert len(tokenized_sents) == len(weight_list)
    num_words = len(tokenized_sents)
    e_test_list=[]
    if (embeddings_type == "elmo" or embeddings_type == "elmo_sectioned"):
        # assert num_words == embeddings_list.shape[1]
        sum = torch.zeros((3, 1024))
        for i in range(0, 3):
            for j in range(0, num_words):
                if(sents_tokened_tagged[j][1] in considered_tags):
                    e_test=embeddings_list[i][j]
                    e_test_list.append(e_test)
                    sum[i] += e_test * weight_list[j]

            sum[i] = sum[i] / float(num_words)
        return sum
    elif(embeddings_type == "elmo_transformer"):
        sum = torch.zeros((1, 1024))
        for i in range(0, 1):
            for j in range(0, num_words):
                if(sents_tokened_tagged[j][1] in considered_tags):
                    e_test=embeddings_list[i][j]
                    e_test_list.append(e_test)
                    sum[i] += e_test * weight_list[j]
            sum[i] = sum[i] / float(num_words)
        return sum
    elif (embeddings_type == "glove"):
        sum = numpy.zeros((1, embeddings_list.shape[2]))
        for i in range(0, 1):
            for j in range(0, num_words):
                if (sents_tokened_tagged[j][1] in considered_tags):
                    e_test = embeddings_list[i][j]
                    e_test_list.append(e_test)
                    sum[i] += e_test * weight_list[j]
            sum[i] = sum[i] / float(num_words)
        return sum

    return 0

def get_candidate_weighted_average(tokenized_sents, weight_list, embeddings_list, start,end,embeddings_type="elmo"):
    # weight_list=get_normalized_weight(weight_list)
    assert len(tokenized_sents) == len(weight_list)
    # num_words = len(tokenized_sents)
    num_words =end - start
    e_test_list=[]
    if (embeddings_type == "elmo" or embeddings_type == "elmo_sectioned"):
        # assert num_words == embeddings_list.shape[1]
        sum = torch.zeros((3, 1024))
        for i in range(0, 3):
            for j in range(start, end):
                e_test=embeddings_list[i][j]
                e_test_list.append(e_test)
                sum[i] += e_test * weight_list[j]
            sum[i] = sum[i] / float(num_words)

        return sum
    elif (embeddings_type == "elmo_transformer"):
        # assert num_words == embeddings_list.shape[1]
        sum = torch.zeros((1, 1024))
        for i in range(0, 1):
            for j in range(start, end):
                e_test = embeddings_list[i][j]
                e_test_list.append(e_test)
                sum[i] += e_test * weight_list[j]
            sum[i] = sum[i] / float(num_words)
        return sum

    elif (embeddings_type == "glove"):
        # assert num_words == embeddings_list.shape[1]
        sum = numpy.zeros((1, embeddings_list.shape[2]))
        for i in range(0, 1):
            for j in range(start, end):
                e_test = embeddings_list[i][j]
                e_test_list.append(e_test)
                sum[i] += e_test * weight_list[j]
            sum[i] = sum[i] / float(num_words)
        return sum

    return 0

def get_oov_weight(tokenized_sents,word2weight,word,method="max_weight"):

    word=wnl.lemmatize(word)

    if(word in word2weight):#
        return word2weight[word]

    if(word in stop_words):
        return 0.0

    if(word in english_punctuations):#The oov_word is a punctuation
        return 0.0

    if (len(word)<=2):#The oov_word makes no sense
        return 0.0

    if(method=="max_weight"):#Return the max weight of word in the tokenized_sents
        max=0.0
        for w in tokenized_sents:
            if(w in word2weight and word2weight[w]>max):
                max=word2weight[w]
        return max
    return 0.0

def get_weight_list(word2weight_pretrain, word2weight_finetune, tokenized_sents, lamda, database=""):
    weight_list = []
    for word in tokenized_sents:
        word = word.lower()

        if(database==""):
            weight_pretrain = get_oov_weight(tokenized_sents, word2weight_pretrain, word, method="max_weight")
            weight=weight_pretrain
        else:
            weight_pretrain = get_oov_weight(tokenized_sents, word2weight_pretrain, word, method="max_weight")
            weight_finetune = get_oov_weight(tokenized_sents, word2weight_finetune, word, method="max_weight")
            weight = lamda * weight_pretrain + (1.0 - lamda) * weight_finetune
        weight_list.append(weight)

    return weight_list

def get_normalized_weight(weight_list):
    sum_weight=0.0
    for weight in weight_list:
        sum_weight+=weight
    if(sum_weight==0.0):
        return weight_list

    for i in range(0,len(weight_list)):
        weight_list[i]/=sum_weight
    return weight_list

def get_word_weight(weightfile="", weightpara=2.7e-4):
    """
    Get the weight of words by word_fre/sum_fre_words
    :param weightfile
    :param weightpara
    :return: word2weight[word]=weight : a dict of word weight
    """
    if weightpara <= 0:  # when the parameter makes no sense, use unweighted
        weightpara = 1.0
    word2weight = {}
    word2fre = {}
    with open(weightfile, encoding='UTF-8') as f:
        lines = f.readlines()
    # sum_num_words = 0
    sum_fre_words = 0
    for line in lines:
        word_fre = line.split()
        # sum_num_words += 1
        if (len(word_fre) == 2):
            word2fre[word_fre[0]] = float(word_fre[1])
            sum_fre_words += float(word_fre[1])
        else:
            print(line)
    for key, value in word2fre.items():
        word2weight[key] = weightpara / (weightpara + value / sum_fre_words)
        # word2weight[key] = 1.0 #method of RVA
    return word2weight

# %tensorflow_version 1.x



# %tensorflow_version 1.x
!pip install tensorflow==1.14
import tensorflow as tf
print(tf.__version__)

import tensorflow as tf
print(tf.__version__)

!pip install bert-serving-server

!wget https://storage.googleapis.com/bert_models/2018_10_18/uncased_L-12_H-768_A-12.zip; unzip uncased_L-12_H-768_A-12.zip

!nohup bert-serving-start -max_seq_len=128 -model_dir=uncased_L-12_H-768_A-12 > out.file 2>&1 &

pip install bert_serving-client

from bert_serving.client import BertClient

bc = BertClient()

#! /usr/bin/env python
# -*- coding: utf-8 -*-
# __author__ = "Sponge"
# Date: 2019/7/29

from bert_serving.client import BertClient
import numpy as np
class WordEmbeddings():
    """
        Concrete class of @EmbeddingDistributor using ELMo
        https://allennlp.org/elmo
    """

    def __init__(self,N=768):

        self.bert = BertClient()
        self.N = N

    def get_tokenized_words_embeddings(self, sents_tokened):
        """
        @see EmbeddingDistributor
        :param tokenized_sents: list of tokenized words string (sentences/phrases)
        :return: ndarray with shape (len(sents), dimension of embeddings)
        """
        bert_embeddings=[]
        for i in range(0, len(sents_tokened)):
            length = len(sents_tokened[i])
            b_e = np.zeros((1, length, self.N))
            b_e[0]=self.bert.encode(sents_tokened[i])
            bert_embeddings.append(b_e)

        return np.array( bert_embeddings)


if __name__ == '__main__':
    Bert=WordEmbeddings()
    sent_tokens=[['I',"love","Rock","and","R","!"],['I',"love","Rock","and","R","!"]]
    embs=Bert.get_tokenized_words_embeddings(sent_tokens)
    print(embs)

pip install --upgrade google-cloud-storage

pip install allennlp==0.9.0

!pip install overrides==3.1.0

from allennlp.commands.elmo import ElmoEmbedder

from allennlp.commands.elmo import ElmoEmbedder

class WordEmbeddings():
    """
        ELMo
        https://allennlp.org/elmo
    """

    def __init__(self,
                 options_file="/content/gdrive/My Drive/elmo_2x4096_512_2048cnn_2xhighway_options.json",
                 weight_file="/content/gdrive/My Drive/elmo_2x4096_512_2048cnn_2xhighway_weights.hdf5", cuda_device=0):
        self.cuda_device=cuda_device
        self.elmo = ElmoEmbedder(options_file, weight_file,cuda_device=self.cuda_device)

    def get_tokenized_words_embeddings(self, sents_tokened):
        """
        @see EmbeddingDistributor
        :param tokenized_sents: list of tokenized words string (sentences/phrases)
        :return: ndarray with shape (len(sents), dimension of embeddings)
        """

        elmo_embedding, elmo_mask = self.elmo.batch_to_embeddings(sents_tokened)
        if(self.cuda_device>-1):
            return elmo_embedding.cpu(), elmo_mask.cpu()
        else:
            return elmo_embedding, elmo_mask

#! /usr/bin/env python
# -*- coding: utf-8 -*-
# __author__ = "Sponge"
# Date: 2019/6/19
import nltk
# from model import input_representation

#GRAMMAR1 is the general way to extract NPs

GRAMMAR1 = """  NP:
        {<NN.*|JJ>*<NN.*>}  # Adjective(s)(optional) + Noun(s)"""

GRAMMAR2 = """  NP:
        {<JJ|VBG>*<NN.*>{0,3}}  # Adjective(s)(optional) + Noun(s)"""

GRAMMAR3 = """  NP:
        {<NN.*|JJ|VBG|VBN>*<NN.*>}  # Adjective(s)(optional) + Noun(s)"""


def extract_candidates(tokens_tagged, no_subset=False):
    """
    Based on part of speech return a list of candidate phrases
    :param text_obj: Input text Representation see @InputTextObj
    :param no_subset: if true won't put a candidate which is the subset of an other candidate
    :return keyphrase_candidate: list of list of candidate phrases: [tuple(string,tuple(start_index,end_index))]
    """
    np_parser = nltk.RegexpParser(GRAMMAR1)  # Noun phrase parser
    keyphrase_candidate = []
    np_pos_tag_tokens = np_parser.parse(tokens_tagged)
    count = 0
    for token in np_pos_tag_tokens:
        if (isinstance(token, nltk.tree.Tree) and token._label == "NP"):
            np = ' '.join(word for word, tag in token.leaves())
            length = len(token.leaves())
            start_end = (count, count + length)
            count += length
            keyphrase_candidate.append((np, start_end))

        else:
            count += 1

    return keyphrase_candidate

# if __name__ == '__main__':
#     #This is an example.
#     sent17 = "NuVox shows staying power with new cash, new market Who says you can't raise cash in today's telecom market? NuVox Communications positions itself for the long run with $78.5 million in funding and a new credit facility"
#     sent10 = "This paper deals with two questions: Does social capital determine innovation in manufacturing firms? If it is the case, to what extent? To deal with these questions, we review the literature on innovation in order to see how social capital came to be added to the other forms of capital as an explanatory variable of innovation. In doing so, we have been led to follow the dominating view of the literature on social capital and innovation which claims that social capital cannot be captured through a single indicator, but that it actually takes many different forms that must be accounted for. Therefore, to the traditional explanatory variables of innovation, we have added five forms of structural social capital (business network assets, information network assets, research network assets, participation assets, and relational assets) and one form of cognitive social capital (reciprocal trust). In a context where empirical investigations regarding the relations between social capital and innovation are still scanty, this paper makes contributions to the advancement of knowledge in providing new evidence regarding the impact and the extent of social capital on innovation at the two decisionmaking stages considered in this study"
#
#     input=input_representation.InputTextObj(sent10,is_sectioned=True,database="Inspec")
#     keyphrase_candidate= extract_candidates(input)
#     for kc in keyphrase_candidate:
#         print(kc)

import nltk
nltk.download('stopwords')

#model.input
#! /usr/bin/env python
# -*- coding: utf-8 -*-
# __author__ = "Sponge"
# Date: 2019/6/19

# from model import extractor
from nltk.corpus import stopwords
stopword_dict = set(stopwords.words('english'))
# from stanfordcorenlp import StanfordCoreNLP
# en_model = StanfordCoreNLP(r'E:\Python_Files\stanford-corenlp-full-2018-02-27',quiet=True)
class InputTextObj:
    """Represent the input text in which we want to extract keyphrases"""

    def __init__(self, en_model, text=""):
        """
        :param is_sectioned: If we want to section the text.
        :param en_model: the pipeline of tokenization and POS-tagger
        :param considered_tags: The POSs we want to keep
        """
        self.considered_tags = {'NN', 'NNS', 'NNP', 'NNPS', 'JJ'}

        self.tokens = []
        self.tokens_tagged = []
        self.tokens = en_model.word_tokenize(text)
        self.tokens_tagged = en_model.pos_tag(text)
        assert len(self.tokens) == len(self.tokens_tagged)
        for i, token in enumerate(self.tokens):
            if token.lower() in stopword_dict:
                self.tokens_tagged[i] = (token, "IN")
        self.keyphrase_candidate = extract_candidates(self.tokens_tagged, en_model)

# if __name__ == '__main__':
#     text = "Adaptive state feedback control for a class of linear systems with unknown bounds of uncertainties The problem of adaptive robust stabilization for a class of linear time-varying systems with disturbance and nonlinear uncertainties is considered. The bounds of the disturbance and uncertainties are assumed to be unknown, being even arbitrary. For such uncertain dynamical systems, the adaptive robust state feedback controller is obtained. And the resulting closed-loop systems are asymptotically stable in theory. Moreover, an adaptive robust state feedback control scheme is given. The scheme ensures the closed-loop systems exponentially practically stable and can be used in practical engineering. Finally, simulations show that the control scheme is effective"
#     ito = InputTextObj(en_model, text)
#     print("OK")

#model.method



#! /usr/bin/env python
# -*- coding: utf-8 -*-
# __author__ = "Sponge"
# Date: 2019/6/19

import numpy as np
import nltk
from nltk.corpus import stopwords
# from model import input_representation
import torch

wnl=nltk.WordNetLemmatizer()
stop_words = set(stopwords.words("english"))

def cos_sim_gpu(x,y):
    assert x.shape[0]==y.shape[0]
    zero_tensor = torch.zeros((1, x.shape[0])).cuda()
    # zero_list = [0] * len(x)
    if x == zero_tensor or y == zero_tensor:
        return float(1) if x == y else float(0)
    xx, yy, xy = 0.0, 0.0, 0.0
    for i in range(x.shape[0]):
        xx += x[i] * x[i]
        yy += y[i] * y[i]
        xy += x[i] * y[i]
    return 1.0 - xy / np.sqrt(xx * yy)

def cos_sim(vector_a, vector_b):
    """
    计算两个向量之间的余弦相似度
    :param vector_a: 向量 a
    :param vector_b: 向量 b
    :return: sim
    """
    vector_a = np.mat(vector_a)
    vector_b = np.mat(vector_b)
    num = float(vector_a * vector_b.T)
    denom = np.linalg.norm(vector_a) * np.linalg.norm(vector_b)
    if(denom==0.0):
        return 0.0
    else:
        cos = num / denom
        sim = 0.5 + 0.5 * cos
        return sim

def cos_sim_transformer(vector_a, vector_b):
    """
    计算两个向量之间的余弦相似度
    :param vector_a: 向量 a
    :param vector_b: 向量 b
    :return: sim
    """
    a = vector_a.detach().numpy()
    b = vector_b.detach().numpy()
    a=np.mat(a)
    b=np.mat(b)

    num = float(a * b.T)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if(denom==0.0):
        return 0.0
    else:
        cos = num / denom
        sim = 0.5 + 0.5 * cos
        return sim

def get_dist_cosine(emb1, emb2, sent_emb_method="elmo",elmo_layers_weight=[0.0,1.0,0.0]):
    sum = 0.0
    assert emb1.shape == emb2.shape
    if(sent_emb_method=="elmo"):

        for i in range(0, 3):
            a = emb1[i]
            b = emb2[i]
            sum += cos_sim(a, b) * elmo_layers_weight[i]
        return sum

    elif(sent_emb_method=="elmo_transformer"):
        sum = cos_sim_transformer(emb1, emb2)
        return sum

    elif(sent_emb_method=="doc2vec"):
        sum=cos_sim(emb1,emb2)
        return sum

    elif (sent_emb_method == "glove"):
        sum = cos_sim(emb1, emb2)
        return sum
    return sum

def get_all_dist(candidate_embeddings_list, text_obj, dist_list):
    '''
    :param candidate_embeddings_list:
    :param text_obj:
    :param dist_list:
    :return: dist_all
    '''

    dist_all={}
    for i, emb in enumerate(candidate_embeddings_list):
        phrase = text_obj.keyphrase_candidate[i][0]
        phrase = phrase.lower()
        phrase = wnl.lemmatize(phrase)
        if(phrase in dist_all):
            #store the No. and distance
            dist_all[phrase].append(dist_list[i])
        else:
            dist_all[phrase]=[]
            dist_all[phrase].append(dist_list[i])
    return dist_all

def get_final_dist(dist_all, method="average"):
    '''
    :param dist_all:
    :param method: "average"
    :return:
    '''

    final_dist={}

    if(method=="average"):

        for phrase, dist_list in dist_all.items():
            sum_dist = 0.0
            for dist in dist_list:
                sum_dist += dist
            if (phrase in stop_words):
                sum_dist = 0.0
            final_dist[phrase] = sum_dist/float(len(dist_list))
        return final_dist

def softmax(x):
    # x = x - np.max(x)
    exp_x = np.exp(x)
    softmax_x = exp_x / np.sum(exp_x)
    return softmax_x


def get_position_score(keyphrase_candidate_list, position_bias):
    length = len(keyphrase_candidate_list)
    position_score ={}
    for i,kc in enumerate(keyphrase_candidate_list):
        np = kc[0]
        p = kc[1][0]
        np = np.lower()
        np = wnl.lemmatize(np)
        if np in position_score:

            position_score[np] += 0.0
        else:
            position_score[np] = 1/(float(i)+1+position_bias)
    score_list=[]
    for np,score in position_score.items():
        score_list.append(score)
    score_list = softmax(score_list)

    i=0
    for np, score in position_score.items():
        position_score[np] = score_list[i]
        i+=1
    return position_score

def SIFRank(text, SIF, en_model, method="average", N=15,
            sent_emb_method="elmo", elmo_layers_weight=[0.0, 1.0, 0.0], if_DS=True, if_EA=True):
    """
    :param text_obj:
    :param sent_embeddings:
    :param candidate_embeddings_list:
    :param sents_weight_list:
    :param method:
    :param N: the top-N number of keyphrases
    :param sent_emb_method: 'elmo', 'glove'
    :param elmo_layers_weight: the weights of different layers of ELMo
    :param if_DS: if take document segmentation(DS)
    :param if_EA: if take  embeddings alignment(EA)
    :return:
    """
    text_obj = InputTextObj(en_model, text)
    sent_embeddings, candidate_embeddings_list = SIF.get_tokenized_sent_embeddings(text_obj,if_DS=if_DS,if_EA=if_EA)
    dist_list = []
    for i, emb in enumerate(candidate_embeddings_list):
        dist = get_dist_cosine(sent_embeddings, emb, sent_emb_method, elmo_layers_weight=elmo_layers_weight)
        dist_list.append(dist)
    dist_all = get_all_dist(candidate_embeddings_list, text_obj, dist_list)
    dist_final = get_final_dist(dist_all, method='average')
    dist_sorted = sorted(dist_final.items(), key=lambda x: x[1], reverse=True)
    return dist_sorted[0:N]

def SIFRank_plus(text, SIF, en_model, method="average", N=15,
            sent_emb_method="elmo", elmo_layers_weight=[0.0, 1.0, 0.0], if_DS=True, if_EA=True, position_bias = 3.4):
    """
    :param text_obj:
    :param sent_embeddings:
    :param candidate_embeddings_list:
    :param sents_weight_list:
    :param method:
    :param N: the top-N number of keyphrases
    :param sent_emb_method: 'elmo', 'glove'
    :param elmo_layers_weight: the weights of different layers of ELMo
    :return:
    """
    text_obj = InputTextObj(en_model, text)
    sent_embeddings, candidate_embeddings_list = SIF.get_tokenized_sent_embeddings(text_obj,if_DS=if_DS,if_EA=if_EA)
    position_score = get_position_score(text_obj.keyphrase_candidate, position_bias)
    average_score = sum(position_score.values()) / (float)(len(position_score))#Little change here
    dist_list = []
    for i, emb in enumerate(candidate_embeddings_list):
        dist = get_dist_cosine(sent_embeddings, emb, sent_emb_method, elmo_layers_weight=elmo_layers_weight)
        dist_list.append(dist)
    dist_all = get_all_dist(candidate_embeddings_list, text_obj, dist_list)
    dist_final = get_final_dist(dist_all, method='average')
    for np,dist in dist_final.items():
        if np in position_score:
            dist_final[np] = dist*position_score[np]/average_score#Little change here
    dist_sorted = sorted(dist_final.items(), key=lambda x: x[1], reverse=True)
    return dist_sorted[0:N]

pip install stanfordcorenlp

import nltk
# from embeddings import sent_emb_sif, word_emb_elmo
# from model.method import SIFRank, SIFRank_plus
from stanfordcorenlp import StanfordCoreNLP
import time

import nltk
nltk.download('wordnet')

nltk.download('omw-1.4')

import nltk
# from embeddings import sent_emb_sif, word_emb_elmo
# from model.method import SIFRank, SIFRank_plus
from stanfordcorenlp import StanfordCoreNLP
import time

#download from https://allennlp.org/elmo
options_file = "/content/gdrive/My Drive/elmo_2x4096_512_2048cnn_2xhighway_options.json"
weight_file = "/content/gdrive/My Drive/elmo_2x4096_512_2048cnn_2xhighway_weights.hdf5"

porter = nltk.PorterStemmer()
# ELMO = WordEmbeddings(options_file, weight_file, cuda_device=0)
ELMO = WordEmbeddings(options_file, weight_file, cuda_device=0)
SIF = SentEmbeddings(ELMO, lamda=1.0)
en_model = StanfordCoreNLP(r'/content/gdrive/My Drive/stanford-corenlp',quiet=True)#download from https://stanfordnlp.github.io/CoreNLP/
elmo_layers_weight = [0.0, 1.0, 0.0]

text = "Discrete output feedback sliding mode control of second order systems - a moving switching line approach The sliding mode control systems (SMCS) for which the switching variable is designed independent of the initial conditions are known to be sensitive to parameter variations and extraneous disturbances during the reaching phase. For second order systems this drawback is eliminated by using the moving switching line technique where the switching line is initially designed to pass the initial conditions and is subsequently moved towards a predetermined switching line. In this paper, we make use of the above idea of moving switching line together with the reaching law approach to design a discrete output feedback sliding mode control. The main contributions of this work are such that we do not require to use system states as it makes use of only the output samples for designing the controller. and by using the moving switching line a low sensitivity system is obtained through shortening the reaching phase. Simulation results show that the fast output sampling feedback guarantees sliding motion similar to that obtained using state feedback"
keyphrases = SIFRank(text, SIF, en_model, N=15,elmo_layers_weight=elmo_layers_weight)
keyphrases_ = SIFRank_plus(text, SIF, en_model, N=15, elmo_layers_weight=elmo_layers_weight)
print(keyphrases)
print(keyphrases_)

from google.colab import files

uploaded = files.upload()

import pandas as pd

df = pd.read_csv("labeled_CN_Posts_Alg.csv")

from nltk.stem import PorterStemmer

 
ps = PorterStemmer()

sif_list = []
for text in df['text']:
  keyphrases = SIFRank(text, SIF, en_model, N=5 ,elmo_layers_weight=elmo_layers_weight)
  keywords = [w[0] for w in keyphrases]
  output = []
  for sentence in keywords:
      output.append(" ".join([ps.stem(i) for i in sentence.split()]))

  sif_list.append(output)

df['sif'] = sif_list

df

df['sif']

