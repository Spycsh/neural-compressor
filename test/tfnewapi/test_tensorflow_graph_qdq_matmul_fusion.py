#
#  -*- coding: utf-8 -*-
#
import os
import unittest
import yaml
import numpy as np
import tensorflow.compat.v1 as tf
from tensorflow.python.framework import dtypes
from neural_compressor.adaptor.tensorflow import TensorflowQuery
from neural_compressor.adaptor.tf_utils.util import disable_random

def build_fake_yaml():
    fake_yaml = '''
        model:
          name: fake_yaml
          framework: tensorflow
          inputs: x
          outputs: op_to_store
        device: cpu
        evaluation:
          accuracy:
            metric:
              topk: 1
        tuning:
            strategy:
              name: basic
            accuracy_criterion:
              relative: 0.01
            exit_policy:
              performance_only: True
            workspace:
              path: saved
        '''
    y = yaml.load(fake_yaml, Loader=yaml.SafeLoader)
    with open('fake_yaml.yaml', "w", encoding="utf-8") as f:
        yaml.dump(y, f)
    f.close()


class TestGraphMatMulFusion(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        build_fake_yaml()
        self.op_wise_sequences = TensorflowQuery(local_config_file=os.path.join(
        os.path.dirname(__file__), "../../neural_compressor/adaptor/tensorflow.yaml")).get_eightbit_patterns(True)

    @classmethod
    def tearDownClass(self):
        os.remove('fake_yaml.yaml')

    @disable_random()
    def test_matmul_biasadd_relu_requantize_fusion(self):
        g = tf.Graph()
        with g.as_default():
            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y)
            z = tf.nn.bias_add(z, [1, 2])
            z = tf.nn.relu(z, name='op_to_store')
            found_quantized_matmul = False
            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr['fused_ops'].list.s == [b'BiasAdd', b'Relu', b'Dequantize']:
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_first_matmul_biasadd_relu_fusion(self):
        x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
        y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
        x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
        y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
        z = tf.matmul(x, y)
        z = tf.nn.bias_add(z, [1, 2])
        z = tf.nn.relu(z,  name='op_to_store')

        with tf.Session() as sess:
            sess.run(z, feed_dict={x: x_data, y: y_data})
            float_graph_def = sess.graph.as_graph_def()

            from neural_compressor.experimental import Quantization, common
            quantizer = Quantization('fake_yaml.yaml')
            dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
            quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
            quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
            quantizer.model = float_graph_def
            output_graph = quantizer.fit()

            found_quantized_matmul = False
            for i in output_graph.graph_def.node:
                if i.op == 'QuantizeV2' and i.name == 'MatMul_eightbit_quantize_x' and i.attr["T"].type == dtypes.quint8:
                    found_quantized_matmul = True
                    break
 
            self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_biasadd_requantize_dequantize_fusion(self):
        g = tf.Graph()
        with g.as_default():

            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y)
            z = tf.nn.bias_add(z, [1, 2])
            z = tf.identity(z, name='op_to_store')
            found_quantized_matmul = False
            
            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr["fused_ops"].list.s == [b'BiasAdd', b'Dequantize']:
                        found_quantized_matmul = True
                        break
                        
            self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_biasadd_requantize_dequantize_last_fusion(self):
        g = tf.Graph()
        with g.as_default():

            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y)
            z = tf.nn.bias_add(z, [1, 2], name='op_to_store')
            found_quantized_matmul = False
            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and i.name == 'op_to_store' and \
                       i.attr["fused_ops"].list.s == [b'BiasAdd', b'Dequantize']:
                        found_quantized_matmul = True
                        break
            self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_fusion_with_transpose_b_true(self):
        g = tf.Graph()
        with g.as_default():

            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y, name='no_quant_matmul', transpose_b=True)
            z = tf.nn.relu6(z, name='op_to_store')
            found_quantized_matmul = False

            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul':
                        found_quantized_matmul = True
                        break
            self.assertEqual(found_quantized_matmul, True)
            
    @disable_random()
    def test_matmul_dummybiasadd_relu6_fusion(self):
        g = tf.Graph()
        with g.as_default():

            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y, name='quant_matmul')
            z = tf.nn.relu6(z, name='op_to_store')
            found_quantized_matmul = False

            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and i.name == 'op_to_store':
                        found_quantized_matmul = True
                        break
            self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_with_reshape_transpose(self):
        g = tf.Graph()
        with g.as_default():

            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            transpose = tf.transpose(y, perm=[1, 0])
            reshape = tf.reshape(transpose, [2, 2])
            z = tf.matmul(x, reshape, name='no_quant_matmul')
            z = tf.nn.bias_add(z, [1, 2], name='op_to_store')
            found_quantized_matmul = True

            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()
                for i in output_graph.graph_def.node:
                    if i.op == 'MatMul':
                        found_quantized_matmul = False
                        break
            self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_with_add(self):
        g = tf.Graph()
        with g.as_default():
            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            transpose = tf.transpose(y, perm=[1, 0])
            reshape = tf.reshape(transpose, [2, 2])
            z = tf.matmul(x, reshape, name='no_quant_matmul')
            z = tf.math.add(z, [1, 2], name='op_to_store')
            found_quantized_matmul = True

            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()
                for i in output_graph.graph_def.node:
                    if i.op == 'MatMul':
                        found_quantized_matmul = False
                        break
            self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_biasadd_requantize_dequantize_fusion_with_softmax(self):
        g = tf.Graph()
        with g.as_default():

            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y)
            biasadd = tf.nn.bias_add(z, [1, 2])
            biasadd1 = tf.nn.bias_add(biasadd, [1, 1])

            y1 = tf.constant(x_data, dtype=tf.float32, shape=[2, 2])
            matmul1 = tf.matmul(biasadd1, y1)

            biasadd2 = tf.nn.bias_add(matmul1, [1, 1])

            z = tf.nn.softmax(biasadd2, name='op_to_store')
            found_quantized_matmul = False
            if tf.version.VERSION < "2.2.0":
                found_quantized_matmul = False
            else:
                with tf.Session() as sess:
                    sess.run(z, feed_dict={x: x_data, y: y_data})
                    float_graph_def = sess.graph.as_graph_def()

                    from neural_compressor.experimental import Quantization, common
                    quantizer = Quantization('fake_yaml.yaml')
                    dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                    quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                    quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                    quantizer.model = float_graph_def
                    output_graph = quantizer.fit()

                    count=0
                    for i in output_graph.model.as_graph_def().node:
                        if i.op == '_QuantizedMatMul':
                            count += 1
                    found_quantized_matmul = bool(count > 1)
            self.assertEqual(found_quantized_matmul, False)

    def test_matmul_biasadd_relu_non_const_weight(self):
        g = tf.Graph()
        with g.as_default():

            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.matmul(x, x, name='quant_matmul_non_const_weight')
            biasadd = tf.nn.bias_add(y, [1, 2])
            z = tf.nn.relu(biasadd)
            found_quantized_matmul = True

            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == 'MatMul':
                        found_quantized_matmul = False
                        break
            self.assertEqual(found_quantized_matmul, True)

    def test_matmul_biasadd_non_const_weight(self):
        g = tf.Graph()
        with g.as_default():

            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.matmul(x, x, name='quant_matmul_non_const_weight')
            z = tf.nn.bias_add(y, [1, 2])
            found_quantized_matmul = True

            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == 'MatMul':
                        found_quantized_matmul = False
                        break
            self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_with_dummy_biasadd(self):
        g = tf.Graph()
        with g.as_default():

            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y, name='no_quant_matmul')
            z = tf.identity(z, name='op_to_store')
            found_quantized_matmul = True

            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == 'MatMul':
                        found_quantized_matmul = False
                        break
            self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_first_matmul_addv2_relu_fusion(self):
        x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
        y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
        x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
        y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
        a = tf.matmul(x, y)
        b = tf.matmul(x, y)
        c = tf.nn.relu(b)
        add = tf.raw_ops.AddV2(x=a, y=c, name='addv2')
        z = tf.nn.relu(add,  name='op_to_store')

        with tf.Session() as sess:

            sess.run(z, feed_dict={x: x_data, y: y_data})
            float_graph_def = sess.graph.as_graph_def()

            from neural_compressor.experimental import Quantization, common
            quantizer = Quantization('fake_yaml.yaml')
            dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
            quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
            quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
            quantizer.model = float_graph_def
            output_graph = quantizer.fit()

            found_quantized_matmul = False
            for i in output_graph.graph_def.node:
                if i.op == '_QuantizedMatMul':
                    found_quantized_matmul = True
                    break
 
            self.assertEqual(found_quantized_matmul, True)

    # batchmatmul quantization disabled temporarily for its bad performance
    """
    @disable_random()
    def test_batchmatmulv2_dequantize_fusion(self):
        g = tf.Graph()
        with g.as_default():
            x_data = np.array([[0.1, 0.2], [0.5, 0.6]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.raw_ops.BatchMatMulV2(x=x, y=y)
            z = tf.nn.bias_add(z, [1, 2])
            z = tf.nn.relu(z, name='op_to_store')
            found_quantized_matmul = False
            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()
                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedBatchMatMul':
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_batchmatmulv2_mul_dequantize_fusion(self):
        np_input = np.random.randn(1, 2, 4, 6).astype(np.float32)
        np_filter = np.random.randn(1, 2, 6, 5).astype(np.float32)
        input = tf.compat.v1.placeholder(dtype=tf.float32, shape=(1, 2, 4, 6))
        filter = tf.constant(np_filter)
        mul = tf.constant(0.2)
        z = tf.raw_ops.BatchMatMulV2(x=input, y=filter)
        z = tf.raw_ops.Mul(x=z, y=mul)
        z = tf.nn.relu(z, name='op_to_store')

        with tf.Session() as sess:
            sess.run(z, feed_dict={input: np_input, filter: np_filter})
            float_graph_def = sess.graph.as_graph_def()

            from neural_compressor.experimental import Quantization, common
            quantizer = Quantization('fake_yaml.yaml')
            dataset = quantizer.dataset('dummy', shape=(1, 2, 4, 6), label=True)
            quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
            quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
            quantizer.model = float_graph_def
            output_graph = quantizer.fit()
            found_quantized_matmul = False
            for i in output_graph.graph_def.node:
                if i.op == '_QuantizedBatchMatMul':
                    found_quantized_matmul = True
                    break

            self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_batchmatmulv2_add_dequantize_fusion(self):
        np_input = np.random.randn(1, 2, 4, 6).astype(np.float32)
        np_filter = np.random.randn(1, 2, 6, 5).astype(np.float32)
        np_add = np.random.randn(1, 2, 4, 5).astype(np.float32)
        input = tf.compat.v1.placeholder(dtype=tf.float32, shape=(1, 2, 4, 6))
        filter = tf.constant(np_filter)
        add = tf.constant(np_add)
        z = tf.raw_ops.BatchMatMulV2(x=input, y=filter)
        z = tf.raw_ops.Add(x=z, y=add)
        z = tf.nn.relu(z, name='op_to_store')

        with tf.Session() as sess:
            sess.run(z, feed_dict={input: np_input, filter: np_filter})
            float_graph_def = sess.graph.as_graph_def()

            from neural_compressor.experimental import Quantization, common
            quantizer = Quantization('fake_yaml.yaml')
            dataset = quantizer.dataset('dummy', shape=(1, 2, 4, 6), label=True)
            quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
            quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
            quantizer.model = float_graph_def
            output_graph = quantizer.fit()
            found_quantized_matmul = False
            for i in output_graph.graph_def.node:
                if i.op == '_QuantizedBatchMatMul':
                    found_quantized_matmul = True
                    break

            self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_batchmatmulv2_mul_add_dequantize_fusion(self):
        np_input = np.random.randn(1, 2, 4, 6).astype(np.float32)
        np_filter = np.random.randn(1, 2, 6, 5).astype(np.float32)
        np_add = np.random.randn(1, 2, 4, 5).astype(np.float32)
        input = tf.compat.v1.placeholder(dtype=tf.float32, shape=(1, 2, 4, 6))
        filter = tf.constant(np_filter)
        mul = tf.constant(0.2)
        add = tf.constant(np_add)
        z = tf.raw_ops.BatchMatMulV2(x=input, y=filter)
        z = tf.raw_ops.Mul(x=z, y=mul)
        z = tf.raw_ops.Add(x=z, y=add)
        z = tf.nn.relu(z, name='op_to_store')

        with tf.Session() as sess:
            sess.run(z, feed_dict={input: np_input, filter: np_filter})
            float_graph_def = sess.graph.as_graph_def()

            from neural_compressor.experimental import Quantization, common
            quantizer = Quantization('fake_yaml.yaml')
            dataset = quantizer.dataset('dummy', shape=(1, 2, 4, 6), label=True)
            quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
            quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
            quantizer.model = float_graph_def
            output_graph = quantizer.fit()
            found_quantized_matmul = False
            for i in output_graph.graph_def.node:
                if i.op == '_QuantizedBatchMatMul':
                    found_quantized_matmul = True
                    break

            self.assertEqual(found_quantized_matmul, True)
    """

    @disable_random()
    def test_matmul_biasadd_relu6_fusion(self):
        g = tf.Graph()
        with g.as_default():
            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y)
            z = tf.nn.bias_add(z, [1, 2])
            z = tf.nn.relu6(z, name='op_to_store')
            found_quantized_matmul = False
            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr['fused_ops'].list.s == [b'BiasAdd', b'Relu6', b'Dequantize']:
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_biasadd_leakyrelu_fusion(self):
        g = tf.Graph()
        with g.as_default():
            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y)
            z = tf.nn.bias_add(z, [1, 2])
            z = tf.nn.leaky_relu(z, name='op_to_store')
            found_quantized_matmul = False
            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr['fused_ops'].list.s == [b'BiasAdd', b'LeakyRelu', b'Dequantize']:
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)
    
    @disable_random()
    def test_matmul_biasadd_geluapproximate_fusion(self):
        g = tf.Graph()
        with g.as_default():
            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y)
            z = tf.nn.bias_add(z, [1, 2])
            z = tf.nn.gelu(z, approximate=True, name='op_to_store')
            found_quantized_matmul = False
            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr['fused_ops'].list.s == [b'BiasAdd', b'GeluApproximate', b'Dequantize']:
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_biasadd_geluexact_fusion(self):
        g = tf.Graph()
        with g.as_default():
            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y)
            z = tf.nn.bias_add(z, [1, 2])
            z = tf.nn.gelu(z, name='op_to_store')
            found_quantized_matmul = False
            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr['fused_ops'].list.s == [b'BiasAdd', b'GeluExact', b'Dequantize']:
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_biasadd_elu_fusion(self):
        g = tf.Graph()
        with g.as_default():
            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y)
            z = tf.nn.bias_add(z, [1, 2])
            z = tf.nn.elu(z, name='op_to_store')
            found_quantized_matmul = False
            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr['fused_ops'].list.s == [b'BiasAdd', b'Elu', b'Dequantize']:
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_biasadd_tanh_fusion(self):
        g = tf.Graph()
        with g.as_default():
            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y)
            z = tf.nn.bias_add(z, [1, 2])
            z = tf.math.tanh(z, name='op_to_store')
            found_quantized_matmul = False
            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr['fused_ops'].list.s == [b'BiasAdd', b'Tanh', b'Dequantize']:
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_biasadd_sigmoid_fusion(self):
        g = tf.Graph()
        with g.as_default():
            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y)
            z = tf.nn.bias_add(z, [1, 2])
            z = tf.math.sigmoid(z, name='op_to_store')
            found_quantized_matmul = False
            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr['fused_ops'].list.s == [b'BiasAdd', b'Sigmoid', b'Dequantize']:
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_dummy_biasadd_relu_fusion(self):
        g = tf.Graph()
        with g.as_default():
            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y, name='quant_matmul')
            z = tf.nn.relu(z, name='op_to_store')
            found_quantized_matmul = False

            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr['fused_ops'].list.s == [b'BiasAdd', b'Relu', b'Dequantize']:
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_dummy_biasadd_relu6_fusion(self):
        g = tf.Graph()
        with g.as_default():
            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y)
            z = tf.nn.relu6(z, name='op_to_store')
            found_quantized_matmul = False
            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr['fused_ops'].list.s == [b'BiasAdd', b'Relu6', b'Dequantize']:
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_dummy_biasadd_leakyrelu_fusion(self):
        g = tf.Graph()
        with g.as_default():
            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y)
            z = tf.nn.leaky_relu(z, name='op_to_store')
            found_quantized_matmul = False
            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr['fused_ops'].list.s == [b'BiasAdd', b'LeakyRelu', b'Dequantize']:
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_dummy_biasadd_geluapproximate_fusion(self):
        g = tf.Graph()
        with g.as_default():
            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y)
            z = tf.nn.gelu(z, approximate=True, name='op_to_store')
            found_quantized_matmul = False
            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr['fused_ops'].list.s == [b'BiasAdd', b'GeluApproximate', b'Dequantize']:
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_dummy_biasadd_geluexact_fusion(self):
        g = tf.Graph()
        with g.as_default():
            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y)
            z = tf.nn.gelu(z, approximate=False, name='op_to_store')
            found_quantized_matmul = False
            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr['fused_ops'].list.s == [b'BiasAdd', b'GeluExact', b'Dequantize']:
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_dummy_biasadd_elu_fusion(self):
        g = tf.Graph()
        with g.as_default():
            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y)
            z = tf.nn.elu(z, name='op_to_store')
            found_quantized_matmul = False
            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr['fused_ops'].list.s == [b'BiasAdd', b'Elu', b'Dequantize']:
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_dummy_biasadd_tanh_fusion(self):
        g = tf.Graph()
        with g.as_default():
            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y)
            z = tf.math.tanh(z, name='op_to_store')
            found_quantized_matmul = False
            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr['fused_ops'].list.s == [b'BiasAdd', b'Tanh', b'Dequantize']:
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_dummy_biasadd_sigmoid_fusion(self):
        g = tf.Graph()
        with g.as_default():
            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y)
            z = tf.math.sigmoid(z, name='op_to_store')
            found_quantized_matmul = False
            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr['fused_ops'].list.s == [b'BiasAdd', b'Sigmoid', b'Dequantize']:
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_add_const_fusion(self):
        g = tf.Graph()
        with g.as_default():
            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            transpose = tf.transpose(y, perm=[1, 0])
            reshape = tf.reshape(transpose, [2, 2])
            z = tf.matmul(x, reshape, name='quant_matmul')
            z = tf.math.add(z, [1, 2], name='op_to_store')
            found_quantized_matmul = False

            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr['fused_ops'].list.s == [b'BiasAdd', b'Dequantize']:
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_add_non_const_fusion(self):
        g = tf.Graph()
        with g.as_default():
            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            transpose = tf.transpose(y, perm=[1, 0])
            reshape = tf.reshape(transpose, [2, 2])
            z = tf.matmul(x, reshape, name='quant_matmul')
            z = tf.math.add(z, x, name='addv2')
            z = tf.nn.relu(z, name='op_to_store')
            found_quantized_matmul = False

            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr['fused_ops'].list.s == [b'Dequantize']:
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_biasadd_add_const_fusion(self):
        g = tf.Graph()
        with g.as_default():

            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y)
            z = tf.nn.bias_add(z, [1, 2])
            z = tf.math.add(z, [1, 2], name='op_to_store')
            found_quantized_matmul = False
            
            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr['fused_ops'].list.s == [b'BiasAdd', b'Dequantize']:
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)

    @disable_random()
    def test_matmul_biasadd_add_non_const_fusion(self):
        g = tf.Graph()
        with g.as_default():

            x_data = np.array([[0.1, 0.2], [0.2, 0.3]])
            y_data = np.array([[1, 2], [3, 4]], dtype=np.float)
            x = tf.placeholder(tf.float32, shape=[2, 2], name='x')
            y = tf.constant(y_data, dtype=tf.float32, shape=[2, 2])
            z = tf.matmul(x, y)
            z = tf.nn.bias_add(z, [1, 2])
            z = tf.math.add(z, x, name='op_to_store')
            found_quantized_matmul = False
            
            with tf.Session() as sess:
                sess.run(z, feed_dict={x: x_data, y: y_data})
                float_graph_def = sess.graph.as_graph_def()

                from neural_compressor.experimental import Quantization, common
                quantizer = Quantization('fake_yaml.yaml')
                dataset = quantizer.dataset('dummy', shape=(2, 2), label=True)
                quantizer.calib_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.eval_dataloader = common.DataLoader(dataset, batch_size=2)
                quantizer.model = float_graph_def
                output_graph = quantizer.fit()

                for i in output_graph.graph_def.node:
                    if i.op == '_QuantizedMatMul' and \
                       i.attr['fused_ops'].list.s == [b'BiasAdd', b'Dequantize']:
                        found_quantized_matmul = True
                        break
                self.assertEqual(found_quantized_matmul, True)

if __name__ == '__main__':
    unittest.main()


