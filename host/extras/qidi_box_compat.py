# Publish the Happy Hare gates in the layout of the stock Qidi Box firmware, read by
# OrcaSlicer's "qidi" printer agent and QIDI Studio. Read-only for the Box: it never moves
# anything. The slot chosen in the slicer comes back through value_t<n> (_BOX_APPLY_SLOT_MAP).
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
import os

REFRESH_SECONDS = 5.
# A numeric filament_slot makes the agent look for a preset with filament_id QD_1_0_<number>
# (the Q2 series is 1), which is how one spool is told apart from another of the same material.
SPOOL_ID_OFFSET = 10000
FILAMENT_LIST = "officiall_filas_list.cfg"
SLOTS_PER_BOX = 4
GATE_EMPTY = 0
DEFAULT_COLOR = "FFFFFF"


def read_gates(mmu_status):
    """One dict per gate from printer.mmu, tolerating lists shorter than the gate count."""
    def item(values, index, default):
        return values[index] if index < len(values) else default
    statuses = mmu_status.get('gate_status', [])
    colors = mmu_status.get('gate_color', [])
    materials = mmu_status.get('gate_material', [])
    names = mmu_status.get('gate_filament_name', [])
    spools = mmu_status.get('gate_spool_id', [])
    return [{
        'present': item(statuses, gate, GATE_EMPTY) != GATE_EMPTY,
        'color': (item(colors, gate, "") or DEFAULT_COLOR).lstrip('#').upper(),
        'material': item(materials, gate, "") or "PLA",
        'name': item(names, gate, "") or "",
        'spool': item(spools, gate, -1),
    } for gate in range(len(statuses))]


def slicer_filament(gate):
    spool = gate['spool']
    return SPOOL_ID_OFFSET + spool if isinstance(spool, int) and spool > 0 else gate['material']


def filament_list(gates):
    """The dictionary the agent uses to name a numeric filament_slot, sorted to stay stable."""
    lines = ["[colordict]", "1 = FFFFFF", ""]
    for number in sorted({slicer_filament(gate) for gate in gates if not isinstance(slicer_filament(gate), str)}):
        material = next(g['material'] for g in gates if slicer_filament(g) == number)
        lines += ["[fila%d]" % number, "filament = %s" % material, ""]
    return "\n".join(lines)


def box_count(gates):
    return (len(gates) + SLOTS_PER_BOX - 1) // SLOTS_PER_BOX


def qidi_variables(gates):
    """The save_variables entries the agent reads. A string filament_slot selects the
    newer firmware layout, whose material name lives in multi_color_controller."""
    variables = {'box_count': box_count(gates)}
    for slot, gate in enumerate(gates):
        variables['color_slot%d' % slot] = [gate['color']]
        variables['filament_slot%d' % slot] = slicer_filament(gate)
        variables['vendor_slot%d' % slot] = 0
    return variables


def controller_status(gates):
    box = {'box_count': box_count(gates)}
    for slot, gate in enumerate(gates):
        prefix = 'box%d_' % (slot // SLOTS_PER_BOX)
        index = slot % SLOTS_PER_BOX
        info = '%sfilament_info_%d_' % (prefix, index)
        box['%sbox_inserted_%d' % (prefix, index)] = int(gate['present'])
        box[info + 'filament_type'] = gate['material']
        box[info + 'filament_str'] = gate['name'] or gate['material']
        box[info + 'vendor_str'] = ""
        box[info + 'color_rgb_str'] = [gate['color']]
    return {'box_count': box['box_count'], 'box': box}


class BoxStepperView:
    def __init__(self, compat, slot):
        self.compat = compat
        self.slot = slot

    def get_status(self, eventtime):
        gates = self.compat.gates
        present = self.slot < len(gates) and gates[self.slot]['present']
        return {'runout_button': 0 if present else 1}


class ControllerView:
    def __init__(self, compat):
        self.compat = compat

    def get_status(self, eventtime):
        return controller_status(self.compat.gates)


class QidiBoxCompat:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gates = []
        self.filament_list_text = None
        self.filament_list_path = os.path.join(
            os.path.dirname(self.printer.get_start_args()['config_file']), FILAMENT_LIST)
        slots = config.getint('slots', SLOTS_PER_BOX, minval=1, maxval=16)
        for slot in range(slots):
            self.printer.add_object('box_stepper slot%d' % slot, BoxStepperView(self, slot))
        self.printer.add_object('multi_color_controller', ControllerView(self))
        self.printer.register_event_handler('klippy:ready', self._handle_ready)

    def _handle_ready(self):
        self.reactor.register_timer(self._refresh, self.reactor.NOW)

    def _refresh(self, eventtime):
        try:
            self._publish(eventtime)
        except Exception:
            # A display helper must never take the printer down
            logging.exception("qidi_box_compat: refresh failed")
        return eventtime + REFRESH_SECONDS

    def _publish(self, eventtime):
        mmu = self.printer.lookup_object('mmu', None)
        saved = self.printer.lookup_object('save_variables', None)
        if mmu is None or saved is None:
            return
        self.gates = read_gates(mmu.get_status(eventtime))
        # In memory only: no disk write every few seconds. get_status() hands out this dict,
        # so a change replaces it instead of editing it.
        current = saved.allVariables
        updates = qidi_variables(self.gates)
        if any(current.get(key) != value for key, value in updates.items()):
            saved.allVariables = dict(current, **updates)
        self._write_filament_list(filament_list(self.gates))

    def _write_filament_list(self, text):
        if text == self.filament_list_text:
            return
        temporary = self.filament_list_path + ".tmp"
        with open(temporary, "w") as output:
            output.write(text)
        os.replace(temporary, self.filament_list_path)
        self.filament_list_text = text


def load_config(config):
    return QidiBoxCompat(config)
