package 'Runs' {
    private import ScalarValues::*;

    verification <'TR-1'> 'Run of display heart rate result' :> 'TC-1' {
        subject dut : 'CONF-1';
        attribute build : String = "v1.0.1";
    }
}
