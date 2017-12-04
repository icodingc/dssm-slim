"""
@@_triplet_multi_loss
@@_dssm_loss
#############
@@_dssm_loss_with_ap[min sim{a,p}]
#############
@@_dssm_loss_with_label[label smoothing]
@@_dssm_loss_with_label_noise[label smoothing with Noise]
#############
@@_dssm_learn_loss[learning similarity]
@@_dssm_loss_one_neg[neg=1 with multi examples]
"""
from __future__ import absolute_import
#from __future__ import division
from __future__ import print_function

import tensorflow as tf

from tensorflow.python.ops import array_ops
from tensorflow.python.ops import math_ops
from tensorflow.contrib.framework import deprecated

slim = tf.contrib.slim
##################
### cos distance
##################
def _cosine_distance(a,b):
  a.get_shape().assert_is_compatible_with(b.get_shape())
  return tf.expand_dims(tf.reduce_sum(tf.mul(a,b),1),1)
##################
###  L2 distance
##################
def _euclidean_distance(a,b):
  a.get_shape().assert_is_compatible_with(b.get_shape())
  return tf.expand_dims(tf.reduce_sum(tf.square(tf.sub(a,b)),1),1)
####################################
#Softmax with importance sampling && 
#Deep similar sementic Model   using cosine similarity.
####################################
def _dssm_loss(anchor,positive,negatives,gamma,scope=None):
  with tf.name_scope(scope,'DSSM',[anchor,positive,negatives]):
    rst = [_cosine_distance(anchor,n) for n in [positive]+negatives]
    gamma = tf.convert_to_tensor(gamma,
                                  dtype=anchor.dtype.base_dtype,
                                  name='gamma_smooth')
    # batch*(p+n) 50*3 for dssm
    logits = tf.concat(1,rst)
    print('logits.shape',logits)
    p = tf.nn.softmax(gamma*logits)
    rst_loss = tf.reduce_mean(-tf.log(tf.squeeze(tf.slice(p,[0,0],[-1,1])),name='Dssmloss'))
    slim.losses.add_loss(rst_loss)
    return rst_loss
######################################
#Importance sampling with Uniform(Q)
######################################
def _dssm_loss2(anchor,positive,negatives,gamma,scope=None):
  with tf.name_scope(scope,'dssm_is',[anchor,positive,negatives]):
    rst = [_cosine_distance(anchor,n) for n in [positive]+negatives]
    gamma = tf.convert_to_tensor(gamma,
                                  dtype=anchor.dtype.base_dtype,
                                  name='gamma_smooth')
    # batch*(p+n) 50*3 for dssm
    logits = gamma*tf.concat(1,rst)
    print('logits.shape',logits)
    # Loss_one -\log{P(q/a)}
    sim_pos1 = -tf.squeeze(tf.slice(logits,[0,0],[-1,1]))
    sim_negs = tf.log(tf.reduce_sum(tf.exp(tf.slice(logits,[0,0],[-1,-1])),1))
    # Loss_two \log{\sigma(sim^{+})}
    sim_pos2 = tf.log(1. + tf.exp(sim_pos1))
    rst_loss = tf.reduce_mean(0.8*sim_pos1+sim_negs+0.2*sim_pos2)
    slim.losses.add_loss(rst_loss)
    return rst_loss 
#####################################
#similarity to magnet loss
#M=16, D=4  ==> (batch_size = 64)
#####################################
def _dssm_loss_batch(features,gamma,scope=None):
  with tf.name_scope(scope,'dssm_batch',[features]):
    gamma = tf.convert_to_tensor(gamma,
                                  dtype=features.dtype.base_dtype,
                                  name='gamma_smooth')
    def _get_item_sim(items):
	    a,b,c,d = tf.split(0,4,items)
	    sim1 = _cosine_distance(a,b)
	    sim2 = _cosine_distance(b,c)
	    sim3 = _cosine_distance(c,d)
	    sim4 = _cosine_distance(d,a)
	    return tf.concat(1,[sim1,sim2,sim3,sim4])
    features = tf.reshape(features,[4,16,128])
    # 16 * [1*4*embedding]
    feat_items = tf.split(1,16,features,name='split_item')
    # pos_mat (16*4)
    pos_mat = tf.concat(0,[_get_item_sim(tf.squeeze(items)) for items in feat_items])*gamma
    # (4*16)
    pos_mat = tf.transpose(pos_mat)
    # get neg_mat 4*(16*16)
    neg_mat = []
    for exm in xrange(4):
        ex = features[exm,:,:]
        ex_sim = tf.matmul(ex,ex,transpose_b=True)*gamma
        neg_mat.append(ex_sim)
    #print 'neg_mat',neg_mat
    all_loss = []
    for j in xrange(16):
        for i in xrange(4):
            pos_m = pos_mat[i][j]
            negs_m = neg_mat[i][j]
            numerator = tf.exp(pos_m)
            denominator = numerator+tf.reduce_sum(tf.exp(negs_m))-tf.exp(negs_m[j])
            all_loss.append(-tf.log(numerator/denominator))
    print('example',len(all_loss))
    rst_loss = tf.reduce_mean(all_loss)
    slim.losses.add_loss(rst_loss)
    return rst_loss 
#####################################
#similarity to magnet loss
#M=16, D=4  ==> (16*(12)) = 192..
#####################################
def _dssm_loss_batch_ex(features,gamma,scope=None):
  with tf.name_scope(scope,'dssm_batch',[features]):
    gamma = tf.convert_to_tensor(gamma,
                                  dtype=features.dtype.base_dtype,
                                  name='gamma_smooth')
    def _get_item_sim(items):
	    a,b,c,d = tf.split(0,4,items)
	    sim1 = _cosine_distance(a,b)
	    sim2 = _cosine_distance(b,c)
	    sim3 = _cosine_distance(c,d)
	    sim4 = _cosine_distance(d,a)
	    sim5 = _cosine_distance(a,c)
	    sim6 = _cosine_distance(b,d)
	    #(a,b)(a,c)(a,d) for a
	    #(b,a)(b,c)(b,d) for b
	    #(c,a)(c,b)(c,d) for c
	    #(d,a)(d,b)(d,c) for d
	    return tf.concat(1,[sim1,sim5,sim4,sim1,sim2,sim6,sim5,sim2,sim3,sim4,sim6,sim3])
    features = tf.reshape(features,[4,16,128])
    # 16 * [1*4*embedding]
    feat_items = tf.split(1,16,features,name='split_item')
    pos_mat = tf.concat(0,[_get_item_sim(tf.squeeze(items)) for items in feat_items])*gamma
    # (12*16)
    pos_mat = tf.transpose(pos_mat)
    # get neg_mat 4*(16*16)
    neg_mat = []
    for exm in xrange(4):
        ex = features[exm,:,:]
        ex_sim = tf.matmul(ex,ex,transpose_b=True)*gamma
        neg_mat.append(ex_sim)
    all_loss = []
    for j in xrange(16):
        for i in xrange(12):
            pos_m = pos_mat[i][j]
            # {0,1,2}->0 ,{3,4,5}->1
            # {6,7,8}->2 ,{9,10,11}->3
            negs_m = neg_mat[i/3][j]
            numerator = tf.exp(pos_m)
            denominator = tf.reduce_sum(numerator+tf.exp(negs_m))-tf.exp(negs_m[j])
            all_loss.append(-tf.log(numerator/denominator))
    print('example',len(all_loss))
    rst_loss = tf.reduce_mean(all_loss)
    slim.losses.add_loss(rst_loss)
    return rst_loss 

