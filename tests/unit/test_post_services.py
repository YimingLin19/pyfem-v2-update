import unittest

from pyfem.io import (
    FIELD_KEY_S_AVG,
    FIELD_KEY_S_IP,
    FIELD_KEY_S_PRINCIPAL_IP,
    FIELD_KEY_S_REC,
    FIELD_KEY_S_VM_IP,
    FIELD_KEY_U,
    FIELD_KEY_U_MAG,
    POSITION_ELEMENT_NODAL,
    POSITION_INTEGRATION_POINT,
    POSITION_NODE,
    POSITION_NODE_AVERAGED,
    RESULT_SOURCE_AVERAGED,
    RESULT_SOURCE_DERIVED,
    RESULT_SOURCE_RAW,
    RESULT_SOURCE_RECOVERED,
    ResultField,
)
from pyfem.post import AveragingService, DerivedFieldService, RawFieldService, RecoveryService
from pyfem.post.common import (
    FIELD_METADATA_KEY_AVERAGING_GROUPS,
    FIELD_METADATA_KEY_BASE_TARGET_KEYS,
    FIELD_METADATA_KEY_DERIVED_FROM,
    FIELD_METADATA_KEY_OWNER_ELEMENT_KEYS,
    FIELD_METADATA_KEY_RECOVERY_SOURCE_FIELD,
)


class PostServicesTests(unittest.TestCase):
    """???????????????"""

    def test_raw_and_recovery_services_preserve_contract(self) -> None:
        element_outputs = {
            "part-1.e1": {
                "type_key": "CPS4",
                "scope_name": "part-1",
                "section_name": "sec-1",
                "material_name": "mat-1",
                "averaging_weight": 2.0,
                "integration_points": (
                    {
                        "target_key": "part-1.e1.ip1",
                        "natural_coordinates": (-0.57735, -0.57735),
                        "sample_weight": 0.5,
                        "strain": (1.0, 2.0, 3.0),
                        "stress": (10.0, 20.0, 30.0),
                    },
                    {
                        "target_key": "part-1.e1.ip2",
                        "natural_coordinates": (0.57735, -0.57735),
                        "sample_weight": 0.5,
                        "strain": (4.0, 5.0, 6.0),
                        "stress": (40.0, 50.0, 60.0),
                    },
                    {
                        "target_key": "part-1.e1.ip3",
                        "natural_coordinates": (0.57735, 0.57735),
                        "sample_weight": 0.5,
                        "strain": (7.0, 8.0, 9.0),
                        "stress": (70.0, 80.0, 90.0),
                    },
                    {
                        "target_key": "part-1.e1.ip4",
                        "natural_coordinates": (-0.57735, 0.57735),
                        "sample_weight": 0.5,
                        "strain": (10.0, 11.0, 12.0),
                        "stress": (100.0, 110.0, 120.0),
                    },
                ),
                "recovery": {
                    "target_keys": (
                        "part-1.e1.n1",
                        "part-1.e1.n2",
                        "part-1.e1.n3",
                        "part-1.e1.n4",
                    ),
                    "base_target_keys": {
                        "part-1.e1.n1": "part-1.n1",
                        "part-1.e1.n2": "part-1.n2",
                        "part-1.e1.n3": "part-1.n3",
                        "part-1.e1.n4": "part-1.n4",
                    },
                    "extrapolation_matrix": (
                        (1.0, 0.0, 0.0, 0.0),
                        (0.0, 1.0, 0.0, 0.0),
                        (0.0, 0.0, 1.0, 0.0),
                        (0.0, 0.0, 0.0, 1.0),
                    ),
                },
            }
        }

        raw_fields = {field.name: field for field in RawFieldService().build_fields(element_outputs)}
        recovered_fields = {field.name: field for field in RecoveryService().build_fields(element_outputs)}

        self.assertEqual(raw_fields[FIELD_KEY_S_IP].position, POSITION_INTEGRATION_POINT)
        self.assertEqual(raw_fields[FIELD_KEY_S_IP].source_type, RESULT_SOURCE_RAW)
        self.assertEqual(raw_fields[FIELD_KEY_S_IP].target_count, 4)
        self.assertEqual(
            raw_fields[FIELD_KEY_S_IP].metadata[FIELD_METADATA_KEY_OWNER_ELEMENT_KEYS]["part-1.e1.ip1"],
            "part-1.e1",
        )
        self.assertEqual(recovered_fields[FIELD_KEY_S_REC].position, POSITION_ELEMENT_NODAL)
        self.assertEqual(recovered_fields[FIELD_KEY_S_REC].source_type, RESULT_SOURCE_RECOVERED)
        self.assertEqual(recovered_fields[FIELD_KEY_S_REC].target_count, 4)
        self.assertEqual(
            recovered_fields[FIELD_KEY_S_REC].metadata[FIELD_METADATA_KEY_BASE_TARGET_KEYS]["part-1.e1.n1"],
            "part-1.n1",
        )
        self.assertEqual(
            recovered_fields[FIELD_KEY_S_REC].metadata[FIELD_METADATA_KEY_RECOVERY_SOURCE_FIELD],
            FIELD_KEY_S_IP,
        )

    def test_averaging_service_breaks_domains_on_shared_base_node(self) -> None:
        recovered_field = ResultField(
            name=FIELD_KEY_S_REC,
            position=POSITION_ELEMENT_NODAL,
            values={
                "part-1.e1.n2": {"S11": 10.0, "S22": 0.0, "S12": 0.0},
                "part-1.e2.n2": {"S11": 20.0, "S22": 0.0, "S12": 0.0},
            },
            source_type=RESULT_SOURCE_RECOVERED,
            component_names=("S11", "S22", "S12"),
            metadata={
                FIELD_METADATA_KEY_BASE_TARGET_KEYS: {
                    "part-1.e1.n2": "part-1.n2",
                    "part-1.e2.n2": "part-1.n2",
                },
                "averaging_domains": {
                    "part-1.e1.n2": {"scope_name": "part-1", "section_name": "sec-left", "material_name": "mat-left"},
                    "part-1.e2.n2": {"scope_name": "part-1", "section_name": "sec-right", "material_name": "mat-right"},
                },
                "averaging_weights": {
                    "part-1.e1.n2": 1.0,
                    "part-1.e2.n2": 2.0,
                },
            },
        )

        averaged_field = AveragingService().build_fields(recovered_field)[0]
        interface_targets = [
            target_key
            for target_key, base_target_key in averaged_field.metadata[FIELD_METADATA_KEY_BASE_TARGET_KEYS].items()
            if base_target_key == "part-1.n2"
        ]

        self.assertEqual(averaged_field.position, POSITION_NODE_AVERAGED)
        self.assertEqual(averaged_field.source_type, RESULT_SOURCE_AVERAGED)
        self.assertEqual(len(interface_targets), 2)
        self.assertEqual(len(set(averaged_field.metadata[FIELD_METADATA_KEY_AVERAGING_GROUPS][key] for key in interface_targets)), 2)

    def test_derived_service_builds_magnitude_von_mises_and_principal_fields(self) -> None:
        field_registry = {
            FIELD_KEY_U: ResultField(
                name=FIELD_KEY_U,
                position=POSITION_NODE,
                values={"part-1.n1": {"UX": 3.0, "UY": 4.0}},
            ),
            FIELD_KEY_S_IP: ResultField(
                name=FIELD_KEY_S_IP,
                position=POSITION_INTEGRATION_POINT,
                values={"part-1.e1.ip1": {"S11": 10.0, "S22": 0.0, "S12": 0.0}},
                component_names=("S11", "S22", "S12"),
            ),
        }

        derived_fields = {field.name: field for field in DerivedFieldService().build_fields(field_registry)}

        self.assertEqual(derived_fields[FIELD_KEY_U_MAG].source_type, RESULT_SOURCE_DERIVED)
        self.assertEqual(derived_fields[FIELD_KEY_U_MAG].values["part-1.n1"]["MAGNITUDE"], 5.0)
        self.assertEqual(derived_fields[FIELD_KEY_U_MAG].metadata[FIELD_METADATA_KEY_DERIVED_FROM], FIELD_KEY_U)
        self.assertEqual(derived_fields[FIELD_KEY_S_VM_IP].source_type, RESULT_SOURCE_DERIVED)
        self.assertAlmostEqual(derived_fields[FIELD_KEY_S_VM_IP].values["part-1.e1.ip1"]["MISES"], 10.0)
        principal = derived_fields[FIELD_KEY_S_PRINCIPAL_IP].values["part-1.e1.ip1"]
        self.assertEqual(principal["P1"], 10.0)
        self.assertEqual(principal["P2"], 0.0)
        self.assertEqual(principal["P3"], 0.0)
        self.assertEqual(derived_fields[FIELD_KEY_S_PRINCIPAL_IP].metadata[FIELD_METADATA_KEY_DERIVED_FROM], FIELD_KEY_S_IP)


if __name__ == "__main__":
    unittest.main()
