__author__ = 'Ivan Kondov'
__email__ = 'ivan.kondov@kit.edu'
__copyright__ = 'Copyright 2016, Karlsruhe Institute of Technology'

from fireworks import Firework
from fireworks.core.firework import FWAction, FireTaskBase
from fireworks.utilities.fw_utilities import explicit_serialize


class CommandLineTask(FireTaskBase):
    """
    A Firetask to execute external commands in a shell

    Required params:
        - command_spec (dict): a dictionary specification of the command
          (see below for details)

    Optional params:
        - inputs ([str]): list of labels, one for each input argument
        - outputs ([str]): list of labels, one for each output argument
        - chunk_numer (int): the serial number of the Firetask 
          when it is part of a series generated by a ForeachTask

    command_spec = {
        'command': [str], # mandatory
        label_1: dict_1, # optional
        label_2: dict_2, # optional
        ...
    }
    The *command* is a list of string representation of the command as to be 
    used with subprocess package. The optional keys label_1, label_2, etc. are 
    the actual labels used in the inputs and outputs. The dictionaries dict_1,
    dict_2, etc. have the following schema:
    {
        'binding': {
            prefix: str or None,
            separator: str or None
        }
        'source': {
            'type': 'path' or 'string' or 'identifier'
                     or 'stdin' or 'stdout' or 'stderr' or None
            'value': str
        }
        'target': {
            'type': 'path' or 'string' or 'identifier'
                     or 'stdin' or 'stdout' or 'stderr' or None
            'value': str
        }
    }
    """

    _fw_name = 'CommandLineTask'
    required_params = ['command_spec']
    optional_params = ['inputs', 'outputs', 'chunk_number']

    def run_task(self, fw_spec):
        cmd_spec = self['command_spec']
        ilabels = self.get('inputs')
        olabels = self.get('outputs')
        if ilabels is None:
            ilables = []
        if olabels is None:
            olables = []
        inputs = []
        outputs = []
        for ios, labels in zip([inputs, outputs], [ilabels, olabels]):
            # cmd_spec: {label: {{binding: {}}, {source: {}}, {target: {}}}}
            for l in labels:
                inp = {}
                for key in ['binding', 'source', 'target']:
                    if key in cmd_spec[l].keys():
                        item = cmd_spec[l][key]
                        if isinstance(item, str): # replace with basestring
                            inp[key] = fw_spec[item]
                        elif isinstance(item, dict):
                            inp[key] = item
                        else:
                            raise ValueError
                ios.append(inp)
        command = cmd_spec['command']

        outlist = self.command_line_tool(command, inputs, outputs)

        if len(outlist) > 0:
            if self.get('chunk_number') is not None:
                mod_spec = []
                if len(olabels) > 1:
                    assert len(olabels) == len(outlist)
                    for ol, out in zip(olabels, outlist):
                        for item in out:
                            mod_spec.append({'_push': {ol: item}})
                else:
                    for out in outlist:
                        mod_spec.append({'_push': {olabels[0]: out}})
                return FWAction(mod_spec=mod_spec)
            else:
                output_dict = {}
                for ol, out in zip(olabels, outlist):
                    output_dict[ol] = out
                return FWAction(update_spec=output_dict)
        else:
            return FWAction()

    def command_line_tool(self, command, inputs=None, outputs=None):
        """
        This function composes and executes a command line from provided
        specifications.

        Required parameters:
            - command ([str]): the command as to be passed to subprocess.Popen

        Optional parameters:
            - inputs ([dict]): list of the specifications for inputs
            - outputs ([dict]): list of the specifications for outputs

        Returns:
            - list of target dictionaries for each output:
                'target': {
                    'type': 'path' or 'string' or 'identifier'
                             or 'stdin' or 'stdout' or 'stderr' or None
                    'value': str
                }
            If outputs is None then an empty list is returned.
        """
        import os
        import uuid
        from subprocess import Popen, PIPE
        from shutil import copyfile

        def set_binding(arg):
            argstr = ''
            if 'binding' in arg.keys():
                if 'prefix' in arg['binding'].keys():
                    argstr += arg['binding']['prefix']
                if 'separator' in arg['binding'].keys():
                    argstr += arg['binding']['separator']
            return argstr

        arglist = command
        stdin = None
        stdout = None
        stderr = None
        stdininp = None
        if inputs is not None:
            for arg in inputs:
                argstr = set_binding(arg)
                assert 'source' in arg.keys()
                assert (arg['source']['type'] is not None
                        and len(arg['source']['value']) > 0)
                if 'target' in arg.keys():
                    assert arg['target'] is not None 
                    assert arg['target']['type'] == 'stdin'
                    if arg['source']['type'] == 'path':
                        stdin = open(arg['source']['value'], 'r')
                    elif arg['source']['type'] == 'string':
                        stdin = PIPE
                        stdininp = arg['source']['value'].encode()
                    else:
                        # filepad
                        raise NotImplementedError()
                else:
                    if arg['source']['type'] == 'path':
                        argstr += arg['source']['value']
                    elif arg['source']['type'] == 'string':
                        argstr += arg['source']['value']
                    else:
                        # filepad
                        raise NotImplementedError()
                if len(argstr) > 0:
                    arglist.append(argstr)

        if outputs is not None:
            for arg in outputs:
                argstr = set_binding(arg)
                assert 'target' in arg.keys()
                assert arg['target'] is not None
                if arg['target']['type'] == 'path':
                    assert 'value' in arg['target']
                    assert len(arg['target']['value']) > 0
                    path = arg['target']['value']
                    if os.path.isdir(path):
                        path = os.path.join(path, str(uuid.uuid4()))
                        arg['target']['value'] = path
                    if arg['source']['type'] == 'stdout':
                        stdout = open(path, 'w')
                    elif arg['source']['type'] == 'stderr':
                        stderr = open(path, 'w')
                    else:
                        argstr += path
                elif arg['target']['type'] == 'string':
                    stdout = PIPE
                else:
                    # filepad
                    raise NotImplementedError()
                if len(argstr) > 0:
                    arglist.append(argstr)

        p = Popen(arglist, stdin=stdin, stderr=stderr, stdout=stdout)
        res = p.communicate(input=stdininp)

        retlist = []
        if outputs is not None:
            for output in outputs:
                if output['source']['type'] == 'path':
                    copyfile(
                        output['source']['value'],
                        output['target']['value']
                    )
                if output['target']['type'] == 'string':
                    output['target']['value'] = res[0].decode().strip()
                retlist.append(output['target'])

        return retlist


class SingleTask(FireTaskBase):
    __doc__ = """
        This firetask passes 'inputs' to a specified python function and
        stores the 'outputs' to the spec of the current firework and the 
        next firework using FWAction.
    """
    _fw_name = 'SingleTask'
    required_params = ['function']
    optional_params = ['inputs', 'outputs', 'chunk_number']

    def run_task(self, fw_spec):
        node_input = self.get('inputs')
        node_output = self.get('outputs')

        inputs = []
        if type(node_input) in [str, unicode]:
            inputs.append(fw_spec[node_input])
        elif type(node_input) is list:
            for item in node_input:
                inputs.append(fw_spec[item])
        elif node_input is not None:
            raise TypeError('input must be a string or a list')

        foo, bar = self['function'].split('.',2)
        func = getattr(__import__(foo), bar)
        outputs = func(*inputs)

        if node_output is None:
            return FWAction()

        if type(outputs) == tuple:
            if type(node_output) == list:
                output_dict = {}
                for (index, item) in enumerate(node_output):
                    output_dict[item] = outputs[index]
            else:
                output_dict = {node_output: outputs}
            return FWAction(update_spec=output_dict)
        else:
            if self.get('chunk_number') is not None:
                if isinstance (outputs, list):
                    mod_spec = [{'_push': {node_output: item}} for item in outputs]
                else:
                    mod_spec = [{'_push': {node_output: outputs}}]
                return FWAction(mod_spec=mod_spec)
            else:
                return FWAction(update_spec={node_output: outputs})


class ForeachTask(FireTaskBase):
    __doc__ = """
        This firetask branches the workflow creating parallel fireworks 
        using FWAction: one firework for each element or each chunk from the 
        'split' list.
    """
    _fw_name = 'ForeachTask'
    required_params = ['function', 'split', 'inputs']
    optional_params = ['outputs', 'number of chunks']

    def run_task(self, fw_spec):
        split_input = self['split']
        node_input = self['inputs']
        if type(split_input) not in [str, unicode]:
            raise TypeError('the "split" argument must be a string')
        if type(fw_spec[split_input]) is not list:
            raise TypeError('the "split" argument must point to a list')
        if type(node_input) is list:
            if split_input not in node_input:
                raise ValueError('the "split" argument must be in argument list')
        else:
            if split_input != node_input:
                raise ValueError('the "split" argument must be in argument list')

        split_field = fw_spec[split_input]
        lensplit = len(split_field)
        if lensplit < 1:
            print(self._fw_name, 'error: input to split is empty:', split_input)
            return FWAction(defuse_workflow=True)

        nchunks = self.get('number of chunks')
        if not nchunks: nchunks = lensplit
        chunklen = lensplit / nchunks
        if lensplit % nchunks > 0:
            chunklen = chunklen + 1
        chunks = [split_field[i:i+chunklen] for i in xrange(0, lensplit, chunklen)]

        fireworks = []
        for index in range(len(chunks)):
            spec = fw_spec.copy()
            spec[split_input] = chunks[index]
            fireworks.append(
                Firework(
                    SingleTask(
                        function = self['function'],
                        inputs = node_input,
                        outputs = self.get('outputs'), 
                        chunk_number = index
                    ),
                    spec = spec,
                    name = self._fw_name + ' ' + str(index)
                )
            )
        return FWAction(detours=fireworks)


class JoinDictTask(FireTaskBase):
    __doc__ = """
        This firetask combines specified spec fields into a new dictionary
    """
    _fw_name = 'JoinDictTask'
    required_params = ['inputs', 'outputs']
    optional_params = ['rename']

    def run_task(self, fw_spec):

        if type(self['outputs']) not in [str, unicode]:
            raise TypeError('"outputs" must be a single string item')

        if self['outputs'] not in fw_spec.keys():
            outputs = {}
        elif type(fw_spec[self['outputs']]) is dict:
            outputs = fw_spec[self['outputs']]
        else:
            raise TypeError('"outputs" exists but is not a dictionary')

        for item in self['inputs']:
            if self.get('rename') and item in self['rename']:
                outputs[self['rename'][item]] = fw_spec[item]
            else:
                outputs[item] = fw_spec[item]

        return FWAction(update_spec={self['outputs']: outputs})


class JoinListTask(FireTaskBase):
    __doc__ = """
        This firetask combines specified spec fields into a new list
    """
    _fw_name = 'JoinListTask'
    required_params = ['inputs', 'outputs']

    def run_task(self, fw_spec):

        if type(self['outputs']) not in [str, unicode]:
            raise TypeError('"outputs" must be a single string item')
            
        if self['outputs'] not in fw_spec.keys():
            outputs = []
        elif type(fw_spec[self['outputs']]) is list:
            outputs = fw_spec[self['outputs']]
        else:
            raise TypeError('"outputs" exists but is not a list')

        for item in self['inputs']:
            outputs.append(fw_spec[item])

        return FWAction(update_spec={self['outputs']: outputs})


class ImportDataTask(FireTaskBase):
    __doc__ = """
    Update the spec with data from file in a nested dictionary at a position 
    specified by a mapstring = maplist[0]/maplist[1]/...
    i.e. dct[maplist[0]][maplist[1]]... = data
    """

    _fw_name = 'ImportDataTask'
    required_params = ['filename', 'mapstring']
    optional_params = []

    def run_task(self, fw_spec):
        from functools import reduce
        import operator
        import json

        filename = self['filename']
        mapstring = self['mapstring']
        assert isinstance(filename, str) or isinstance(filename, unicode)
        assert isinstance(mapstring, str) or isinstance(mapstring, unicode)
        maplist = mapstring.split('/')

        with open(filename, 'r') as inp:
            data = json.load(inp)

        leaf = reduce(operator.getitem, maplist[:-1], fw_spec)
        if isinstance(data, dict):
            if maplist[-1] not in list(leaf.keys()):
                leaf[maplist[-1]] = data
            else:
                leaf[maplist[-1]].update(data)
        else:
            leaf[maplist[-1]] = data

        return FWAction(update_spec={maplist[0]: fw_spec[maplist[0]]})

