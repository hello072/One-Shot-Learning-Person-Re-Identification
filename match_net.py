import numpy as np
import time
use_conv = True
refresh = 1e3
avg_loss = 0.0
mb_dim = 32 #training examples per minibatch
w_dim = 64  #width of image
h_dim = 128  #height of image
y_dim = 5  #possible classes
n_samples_per_class = 1 #samples of each class
n_samples = y_dim*n_samples_per_class #total number of labeled samples
eps = 1e-10 #term added for numerical stability of log computations
tie = True #tie the weights of the query network to the labeled network
x_i_learn = True #toggle learning for the query network
learning_rate = 4e-5 #1e-1

data = np.load('data.npy')
#data = np.reshape(data,[-1,20,28,28]) #each of the 300 classes has 20 examples
data = np.random.permutation(data) #shuffling
train_data = data[:250]
test_data = data[250:]

'''
    Samples a minibatch of size mb_dim. Each training example contains
    n_samples labeled samples, such that n_samples_per_class samples
    come from each of y_dim randomly chosen classes. An additional example
    one one of these classes is then chosen to be the query, and its label
    is the target of the network.
'''
def get_minibatch(test=False):
    if test:
        cur_data = test_data
        print('testing')
    else:
        cur_data = train_data
    mb_x_i = np.zeros((mb_dim,n_samples,h_dim,w_dim,3))
    mb_y_i = np.zeros((mb_dim,n_samples))
    mb_x_hat = np.zeros((mb_dim,h_dim,w_dim,3),dtype=np.int)
    mb_y_hat = np.zeros((mb_dim,),dtype=np.int)
    for i in range(mb_dim):
        ind = 0
        pinds = np.random.permutation(n_samples) #ex: 3 2 0 4 1
        classes = np.random.choice(len(cur_data),y_dim,False) #ex: 280 273 22 227 35
        x_hat_class = np.random.randint(y_dim) #ex: 3
        for j,cur_class in enumerate(classes): #each class
            example_inds = np.random.choice(len(cur_data[cur_class]),n_samples_per_class,False)
            for eind in example_inds:
                #mb_x_i[i,pinds[ind],:,:,0] = np.rot90(cur_data[cur_class][eind],np.random.randint(4))
                mb_x_i[i,pinds[ind]] = cur_data[cur_class][eind]
                mb_y_i[i,pinds[ind]] = j
                ind +=1
            if j == x_hat_class:
                #mb_x_hat[i,:,:,0] = np.rot90(cur_data[cur_class][np.random.choice(cur_data.shape[1])],np.random.randint(4))
                mb_x_hat[i] = cur_data[cur_class][np.random.choice(len(cur_data[cur_class]))]
                mb_y_hat[i] = j
    return mb_x_i,mb_y_i,mb_x_hat,mb_y_hat



                



import tensorflow as tf
flags = tf.app.flags
FLAGS = flags.FLAGS
flags.DEFINE_string('summary_dir', '/tmp/oneshot_logs', 'Summaries directory')
if tf.gfile.Exists(FLAGS.summary_dir):
    tf.gfile.DeleteRecursively(FLAGS.summary_dir)
    tf.gfile.MakeDirs(FLAGS.summary_dir)


x_hat = tf.placeholder(tf.float32,shape=[None,h_dim,w_dim,3])
x_i = tf.placeholder(tf.float32,shape=[None,n_samples,h_dim,w_dim,3])
y_i_ind = tf.placeholder(tf.int32,shape=[None,n_samples])
y_i = tf.one_hot(y_i_ind,y_dim)
y_hat_ind = tf.placeholder(tf.int32,shape=[None])
y_hat = tf.one_hot(y_hat_ind,y_dim)
'''
    creates a stack of 4 layers. Each layer contains a
    3x3 conv layers, batch normalization, retified activation,
    and then 2x2 max pooling. The net effect is to tranform the
    mb_dimx28x28x1 images into a mb_dimx1x1x64 embedding, the extra
    dims are removed, resulting in mb_dimx64.
'''
def make_conv_net(inp,scope,reuse=False,stop_grad=False):
    with tf.variable_scope(scope) as varscope:
        if reuse: varscope.reuse_variables()
        cur_input = inp
        cur_filters = 3
        df_filters = 100
        for i in range(5):
            with tf.variable_scope('conv'+str(i)):
                W = tf.get_variable('W',[3,3,cur_filters,df_filters*(i+1)],initializer=tf.contrib.layers.xavier_initializer())
                b = tf.get_variable('b',df_filters*(i+1),initializer=tf.constant_initializer(0.0))
                cur_filters = df_filters*(i+1)
                beta = tf.get_variable('beta',[df_filters*(i+1)],initializer=tf.constant_initializer(0.0))
                gamma = tf.get_variable('gamma',[df_filters*(i+1)],initializer=tf.constant_initializer(1.0))
                pre_norm = tf.nn.bias_add(tf.nn.conv2d(cur_input,W,strides=[1,1,1,1],padding='SAME'),b)
                mean,variance = tf.nn.moments(pre_norm,[0,1,2])
                post_norm = tf.nn.batch_normalization(pre_norm,mean,variance,beta,gamma,eps)
                conv = tf.nn.relu(post_norm)
                cur_input = tf.nn.max_pool(conv,ksize=[1,2,2,1],strides=[1,2,2,1],padding='VALID')
        cur_input = tf.contrib.layers.flatten(cur_input)
        hid = tf.layers.dense(cur_input,2048,activation = tf.nn.relu)
        output = tf.layers.dense(hid,1024)
    if stop_grad:
        return tf.stop_gradient(output)
    else:
        return output

def make_dense_net(inp,scope,reuse=False,stop_grad=False):
    with tf.variable_scope(scope) as varscope:
        if reuse: varscope.reuse_variables()
        cur_input = tf.contrib.layers.flatten(inp)
        hid = tf.layers.dense(cur_input,1000,activation = tf.nn.relu)
        output = tf.layers.dense(hid,64)
    if stop_grad:
        return tf.stop_gradient(output)
    else:
        return output
'''
    assemble a computational graph for processing minibatches of the n_samples labeled examples and one unlabeled sample.
    All labeled examples use the same convolutional network, whereas the unlabeled sample defaults to using different parameters.
    After using the convolutional networks to encode the input, the pairwise cos similarity is computed. The normalized version of this
    is used to weight each label's contribution to the queried label prediction.
'''
scope = 'encode_x'
if use_conv:
    x_hat_encode = make_conv_net(x_hat,scope)
else:
    x_hat_encode = make_dense_net(x_hat,scope)
#x_hat_inv_mag = tf.rsqrt(tf.clip_by_value(tf.reduce_sum(tf.square(x_hat_encode),1,keep_dims=True),eps,float("inf")))
cos_sim_list = []
if not tie:
    scope = 'encode_x_i'
for i in range(n_samples):
    if use_conv:
        x_i_encode = make_conv_net(x_i[:,i,:,:,:],scope,tie or i > 0,not x_i_learn)
    else:
        x_i_encode = make_dense_net(x_i[:,i,:,:,:],scope,tie or i > 0,not x_i_learn)
    x_i_inv_mag = tf.rsqrt(tf.clip_by_value(tf.reduce_sum(tf.square(x_i_encode),1,keep_dims=True),eps,float("inf")))
    dotted = tf.squeeze(
        tf.matmul(tf.expand_dims(x_hat_encode,1),tf.expand_dims(x_i_encode,2)),[1,])
    cos_sim_list.append(dotted
            *x_i_inv_mag)
            #*x_hat_inv_mag
cos_sim = tf.concat(axis=1,values=cos_sim_list)
tf.summary.histogram('cos sim',cos_sim)
weighting = tf.nn.softmax(cos_sim)
label_prob = tf.squeeze(tf.matmul(tf.expand_dims(weighting,1),y_i))
tf.summary.histogram('label prob',label_prob)

top_k = tf.nn.in_top_k(label_prob,y_hat_ind,1)
acc = tf.reduce_mean(tf.to_float(top_k))
tf.summary.scalar('train avg accuracy',acc)
correct_prob = tf.reduce_sum(tf.log(tf.clip_by_value(label_prob,eps,1.0))*y_hat,1)
loss = tf.reduce_mean(-correct_prob,0)
tf.summary.scalar('loss',loss)
#optim = tf.train.GradientDescentOptimizer(learning_rate)
optim = tf.train.AdamOptimizer(learning_rate)
grads = optim.compute_gradients(loss)
grad_summaries = [tf.summary.histogram(v.name,g) if g is not None else '' for g,v in grads]
train_step = optim.apply_gradients(grads)

#testing stuff
test_acc = tf.reduce_mean(tf.to_float(top_k))


'''
    End of the construction of the computational graph. The remaining code runs training steps.
'''

sess_config = tf.ConfigProto()
sess_config.gpu_options.allow_growth = True
sess_config.allow_soft_placement=True
sess = tf.Session(config=sess_config)
merged = tf.summary.merge_all()
test_summ = tf.summary.scalar('test avg accuracy',test_acc)
writer = tf.summary.FileWriter(FLAGS.summary_dir,sess.graph)
sess.run(tf.global_variables_initializer())
for i in range(1,int(1e7)):
    mb_x_i,mb_y_i,mb_x_hat,mb_y_hat = get_minibatch()
    feed_dict = {x_hat: mb_x_hat,
                y_hat_ind: mb_y_hat,
                x_i: mb_x_i,
                y_i_ind: mb_y_i}
    _,mb_loss,summary,ans = sess.run([train_step,loss,merged,cos_sim],feed_dict=feed_dict)
    avg_loss += mb_loss
    if i % int(refresh) == 0:
        mb_x_i,mb_y_i,mb_x_hat,mb_y_hat = get_minibatch(True)
        feed_dict = {x_hat: mb_x_hat,
                    y_hat_ind: mb_y_hat,
                    x_i: mb_x_i,
                    y_i_ind: mb_y_i}
        cur_acc,test_summary = sess.run([test_acc,test_summ],feed_dict=feed_dict)
        writer.add_summary(test_summary,i)
        avg_loss /= float(refresh)
        print(i,'acc: ',cur_acc,'loss: ',avg_loss)
        avg_loss = 0.0
        run_options = tf.RunOptions(trace_level=tf.RunOptions.FULL_TRACE)
        run_metadata = tf.RunMetadata()
        writer.add_run_metadata(run_metadata, 'step%d' % i)
    writer.add_summary(summary,i)
