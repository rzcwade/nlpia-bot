""" Transformer based chatbot dialog engine for answering questions """

import logging
import os
import urllib.request
import uuid
import zipfile
from multiprocessing import cpu_count
from tqdm import tqdm

from simpletransformers.question_answering import QuestionAnsweringModel

from nlpia_bot.etl import scrape_wikipedia
from nlpia_bot.constants import DATA_DIR, USE_CUDA

log = logging.getLogger(__name__)


class DownloadProgressBar(tqdm):
    """ Utility class that adds tqdm progress bar to urllib.request.urlretrieve """

    def update_to(self, b=1, bsize=1, tsize=None):
        if tsize is not None:
            self.total = tsize
        self.update(b * bsize - self.n)


class Bot:
    """ Bot that provides answers to questions given context data containing the answer """

    def __init__(self):
        self.transformer_loggers = []
        for name in logging.root.manager.loggerDict:
            if len(name) >= 11 and name[:11] in ['transformer', 'simpletrans']:
                self.transformer_loggers.append(logging.getLogger(name))
                self.transformer_loggers[-1].setLevel(logging.ERROR)

        url_str = 'https://totalgood.org/midata/models/bert/cased_simpletransformers.zip'
        model_dir = os.path.join(DATA_DIR, 'simple-transformer')
        if not os.path.isdir(model_dir):
            os.mkdir(model_dir)
        
        if (
            not os.path.exists(os.path.join(model_dir, 'config.json'))
            or not os.path.exists(os.path.join(model_dir, 'pytorch_model.bin'))
            or not os.path.exists(os.path.join(model_dir, 'special_tokens_map.json'))
            or not os.path.exists(os.path.join(model_dir, 'tokenizer_config.json'))
            or not os.path.exists(os.path.join(model_dir, 'training_args.bin'))
            or not os.path.exists(os.path.join(model_dir, 'vocab.txt'))
        ):
            zip_local_path = os.path.join(model_dir, 'cased_simpletransformers.zip')
            with DownloadProgressBar(unit='B', unit_scale=True, miniters=1, desc=url_str.split('/')[-1]) as t:
                urllib.request.urlretrieve(url_str, filename=zip_local_path, reporthook=t.update_to)
            with zipfile.ZipFile(zip_local_path, 'r') as zip_file:
                zip_file.extractall(model_dir)
            os.remove(zip_local_path)

        process_count = cpu_count() - 2 if cpu_count() > 2 else 1
        args = {
            'process_count': process_count,
            'output_dir': model_dir,
            'cache_dir': model_dir,
            'no_cache': True,
            'use_cached_eval_features': False,
            'overwrite_output_dir': False,
            'silent': True
        }
    
        self.model = QuestionAnsweringModel('bert', model_dir, args=args, use_cuda=USE_CUDA)

    def encode_input(self, statement, context):
        """
        Packs statement and context strings into expected input format for the model

        >>> bot = Bot()
        >>> encoded = bot.encode_input('statement', 'context')
        >>> assert encoded[0]['qas'][0]['question'] == 'statement'
        >>> assert encoded[0]['context'] == 'context'
        """
        encoded = [{
            'qas': [{
                'id': str(uuid.uuid1()),
                'question': statement
            }],
            'context': context
        }]
        return encoded

    def decode_output(self, output):
        """
        Extracts reply string from the model's prediction output

        >>> bot = Bot()
        >>> bot.decode_output([{'id': 'unique_id', 'answer': 'response'}])
        'response'
        """
        return output[0]['answer']

    def reply(self, statement):
        responses = []
        docs = scrape_wikipedia.scrape_article_texts()
        for context in docs:
            encoded_input = self.encode_input(statement, context)
            encoded_output = self.model.predict(encoded_input)
            decoded_output = self.decode_output(encoded_output)
            if len(decoded_output) > 0:
                responses.append((1, decoded_output))
        return responses
