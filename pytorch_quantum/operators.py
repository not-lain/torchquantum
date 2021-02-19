import torch
import torch.nn as nn
import pytorch_quantum as tq
import pytorch_quantum.functional as tqf
import numpy as np
import logging

from enum import IntEnum
from pytorch_quantum.functional import mat_dict
from abc import ABCMeta
from .macro import C_DTYPE, F_DTYPE

logger = logging.getLogger()


class WiresEnum(IntEnum):
    """Integer enumeration class
    to represent the number of wires
    an operation acts on"""

    AnyWires = -1
    AllWires = 0


AllWires = WiresEnum.AllWires
"""IntEnum: An enumeration which represents all wires in the
subsystem. It is equivalent to an integer with value 0."""

AnyWires = WiresEnum.AnyWires
"""IntEnum: An enumeration which represents any wires in the
subsystem. It is equivalent to an integer with value -1."""


class Operator(nn.Module):
    fixed_ops = [
        'Hadamard',
        'PauliX',
        'PauliY',
        'PauliZ',
        'S',
        'T',
        'SX',
        'CNOT',
        'CZ',
        'CY',
        'SWAP',
        'CSWAP',
        'Toffoli'
    ]

    parameterized_ops = [
        'RX',
        'RY',
        'RZ',
        'PhaseShift',
        'Rot',
        'MultiRZ',
        'CRX',
        'CRY',
        'CRZ',
        'CRot',
        'U1'
    ]

    @property
    def name(self):
        """String for the name of the operator."""
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    def __init__(self):
        super().__init__()
        self.params = None
        self.n_wires = None
        self._name = self.__class__.__name__

    @classmethod
    def _matrix(cls, params):
        raise NotImplementedError

    @property
    def matrix(self):
        return self._matrix(self.params)

    @classmethod
    def _eigvals(cls, params):
        raise NotImplementedError

    @property
    def eigvals(self):
        return self._eigvals(self.params)

    def _get_unitary_matrix(self):
        return self.matrix

    def forward(self, q_device: tq.QuantumDevice, wires, params=None):
        try:
            assert self.name in self.fixed_ops or \
                   self.has_params ^ (params is not None)
        except AssertionError as err:
            logger.exception(f"Parameterized gate either has its "
                             f"own parameters or has input as parameters")
            raise err

        if params is not None:
            self.params = params

        # non-parameterized gate
        if self.params is None:
            if self.n_wires is None:
                self.func(q_device, wires)
            else:
                self.func(q_device, wires, n_wires=self.n_wires)
        else:
            if self.n_wires is None:
                self.func(q_device, wires, params=self.params)
            else:
                self.func(q_device, wires, params=self.params,
                          n_wires=self.n_wires)


class Observable(Operator, metaclass=ABCMeta):
    def __init__(self):
        super().__init__()
        self.return_type = None

    def diagonalizing_gates(self):
        raise NotImplementedError


class Operation(Operator, metaclass=ABCMeta):
    def __init__(self,
                 has_params: bool = False,
                 trainable: bool = False,
                 init_params=None,
                 n_wires=None):
        # n_wires is used in gates that can be applied to arbitrary number
        # of qubits such as MultiRZ
        super().__init__()

        try:
            assert not (trainable and not has_params)
        except AssertionError:
            has_params = True
            logger.warning(f"Module must have parameters to be trainable; "
                           f"Switched 'has_params' to True.")

        self.has_params = has_params
        self.trainable = trainable
        if self.has_params:
            self.params = self.build_params(trainable=self.trainable)
            self.reset_params(init_params)
        self.n_wires = n_wires

    @property
    def matrix(self):
        op_matrix = self._matrix(self.params)

        return op_matrix

    @property
    def eigvals(self):
        op_eigvals = self._eigvals(self.params)

        return op_eigvals

    def init_params(self):
        raise NotImplementedError

    def build_params(self, trainable):
        parameters = nn.Parameter(torch.empty([1, self.num_params],
                                              dtype=F_DTYPE))
        parameters.requires_grad = True if trainable else False
        self.register_parameter(f"{self.name}_params", parameters)
        return parameters

    def reset_params(self, init_params=None):
        if init_params is not None:
            if isinstance(init_params, list):
                for k, init_param in enumerate(init_params):
                    torch.nn.init.constant_(self.params[:, k], init_param)
            else:
                torch.nn.init.constant_(self.params, init_params)
        else:
            torch.nn.init.uniform_(self.params, 0, 2 * np.pi)


class DiagonalOperation(Operation, metaclass=ABCMeta):
    @classmethod
    def _eigvals(cls, params):
        raise NotImplementedError

    @property
    def eigvals(self):
        return super().eigvals

    @classmethod
    def _matrix(cls, params):
        return torch.diag(cls._eigvals(params))


class Hadamard(Observable, Operation, metaclass=ABCMeta):
    num_params = 0
    num_wires = 1
    eigvals = torch.tensor([1, -1], dtype=C_DTYPE)
    matrix = mat_dict['hadamard']
    func = staticmethod(tqf.hadamard)

    @classmethod
    def _matrix(cls, params):
        return cls.matrix

    @classmethod
    def _eigvals(cls, params):
        return cls.eigvals

    def diagonalizing_gates(self):
        return [tq.RY(has_params=True,
                      trainable=False,
                      init_params=-np.pi / 4)]


class PauliX(Observable, metaclass=ABCMeta):
    num_params = 0
    num_wires = 1
    eigvals = torch.tensor([1, -1], dtype=C_DTYPE)
    matrix = mat_dict['paulix']
    func = staticmethod(tqf.paulix)

    @classmethod
    def _matrix(cls, params):
        return cls.matrix

    @classmethod
    def _eigvals(cls, params):
        return cls.eigvals

    def diagonalizing_gates(self):
        return [tq.Hadamard()]


class PauliY(Observable, metaclass=ABCMeta):
    num_params = 0
    num_wires = 1
    eigvals = torch.tensor([1, -1], dtype=C_DTYPE)
    matrix = mat_dict['pauliy']
    func = staticmethod(tqf.pauliy)

    @classmethod
    def _matrix(cls, params):
        return cls.matrix

    @classmethod
    def _eigvals(cls, params):
        return cls.eigvals

    def diagonalizing_gates(self):
        return [tq.PauliZ(), tq.S(), tq.Hadamard()]


class PauliZ(Observable, metaclass=ABCMeta):
    num_params = 0
    num_wires = 1
    eigvals = torch.tensor([1, -1], dtype=C_DTYPE)
    matrix = mat_dict['pauliz']
    func = staticmethod(tqf.pauliz)

    @classmethod
    def _matrix(cls, params):
        return cls.matrix

    @classmethod
    def _eigvals(cls, params):
        return cls.eigvals

    def diagonalizing_gates(self):
        return []


class S(DiagonalOperation, metaclass=ABCMeta):
    num_params = 0
    num_wires = 1
    eigvals = torch.tensor([1, 1j], dtype=C_DTYPE)
    matrix = mat_dict['s']
    func = staticmethod(tqf.s)

    @classmethod
    def _matrix(cls, params):
        return cls.matrix

    @classmethod
    def _eigvals(cls, params):
        return cls.eigvals


class T(DiagonalOperation, metaclass=ABCMeta):
    num_params = 0
    num_wires = 1
    eigvals = torch.tensor([1, 1j], dtype=C_DTYPE)
    matrix = mat_dict['t']
    func = staticmethod(tqf.t)

    @classmethod
    def _matrix(cls, params):
        return cls.matrix

    @classmethod
    def _eigvals(cls, params):
        return cls.eigvals


class SX(Operation, metaclass=ABCMeta):
    num_params = 0
    num_wires = 1
    eigvals = torch.tensor([1, 1j], dtype=C_DTYPE)
    matrix = mat_dict['sx']
    func = staticmethod(tqf.sx)

    @classmethod
    def _matrix(cls, params):
        return cls.matrix

    @classmethod
    def _eigvals(cls, params):
        return cls.eigvals


class CNOT(Operation, metaclass=ABCMeta):
    num_params = 0
    num_wires = 2
    matrix = mat_dict['cnot']
    func = staticmethod(tqf.cnot)

    @classmethod
    def _matrix(cls, params):
        return cls.matrix


class CZ(DiagonalOperation, metaclass=ABCMeta):
    num_params = 0
    num_wires = 2
    eigvals = np.array([1, 1, 1, -1])
    matrix = mat_dict['cz']
    func = staticmethod(tqf.cz)

    @classmethod
    def _matrix(cls, params):
        return cls.matrix

    @classmethod
    def _eigvals(cls, params):
        return cls.eigvals


class CY(Operation, metaclass=ABCMeta):
    num_params = 0
    num_wires = 2
    matrix = mat_dict['cy']
    func = staticmethod(tqf.cy)

    @classmethod
    def _matrix(cls, params):
        return cls.matrix


class SWAP(Operation, metaclass=ABCMeta):
    num_params = 0
    num_wires = 2
    matrix = mat_dict['swap']
    func = staticmethod(tqf.swap)

    @classmethod
    def _matrix(cls, params):
        return cls.matrix


class CSWAP(Operation, metaclass=ABCMeta):
    num_params = 0
    num_wires = 3
    matrix = mat_dict['cswap']
    func = staticmethod(tqf.cswap)

    @classmethod
    def _matrix(cls, params):
        return cls.matrix


class Toffoli(Operation, metaclass=ABCMeta):
    num_params = 0
    num_wires = 3
    matrix = mat_dict['toffoli']
    func = staticmethod(tqf.toffoli)

    @classmethod
    def _matrix(cls, params):
        return cls.matrix


class RX(Operation, metaclass=ABCMeta):
    num_params = 1
    num_wires = 1
    func = staticmethod(tqf.rx)

    @classmethod
    def _matrix(cls, params):
        return tqf.rx_matrix(params)


class RY(Operation, metaclass=ABCMeta):
    num_params = 1
    num_wires = 1
    func = staticmethod(tqf.ry)

    @classmethod
    def _matrix(cls, params):
        return tqf.ry_matrix(params)


class RZ(DiagonalOperation, metaclass=ABCMeta):
    num_params = 1
    num_wires = 1
    func = staticmethod(tqf.rz)

    @classmethod
    def _matrix(cls, params):
        return tqf.rz_matrix(params)


class PhaseShift(DiagonalOperation, metaclass=ABCMeta):
    num_params = 1
    num_wires = 1
    func = staticmethod(tqf.phaseshift)

    @classmethod
    def _matrix(cls, params):
        return tqf.phaseshift_matrix(params)


class Rot(Operation, metaclass=ABCMeta):
    num_params = 3
    num_wires = 1
    func = staticmethod(tqf.rot)

    @classmethod
    def _matrix(cls, params):
        return tqf.rot_matrix(params)


class MultiRZ(DiagonalOperation, metaclass=ABCMeta):
    num_params = 1
    num_wires = AnyWires
    func = staticmethod(tqf.multirz)

    @classmethod
    def _matrix(cls, params, n_wires):
        return tqf.multirz_matrix(params, n_wires)


class CRX(Operation, metaclass=ABCMeta):
    num_params = 1
    num_wires = 2
    func = staticmethod(tqf.crx)

    @classmethod
    def _matrix(cls, params):
        return tqf.crx_matrix(params)


class CRY(Operation, metaclass=ABCMeta):
    num_params = 1
    num_wires = 2
    func = staticmethod(tqf.cry)

    @classmethod
    def _matrix(cls, params):
        return tqf.cry_matrix(params)


class CRZ(Operation, metaclass=ABCMeta):
    num_params = 1
    num_wires = 2
    func = staticmethod(tqf.crz)

    @classmethod
    def _matrix(cls, params):
        return tqf.crz_matrix(params)


class CRot(Operation, metaclass=ABCMeta):
    num_params = 3
    num_wires = 2
    func = staticmethod(tqf.crot)

    @classmethod
    def _matrix(cls, params):
        return tqf.crot_matrix(params)


class U1(DiagonalOperation, metaclass=ABCMeta):
    # U1 is the same as phaseshift
    num_params = 1
    num_wires = 1
    func = staticmethod(tqf.u1)

    @classmethod
    def _matrix(cls, params):
        return tqf.u1_matrix(params)
