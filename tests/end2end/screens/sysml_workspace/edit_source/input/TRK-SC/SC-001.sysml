package 'SC-001' {
    private import 'TRK-SYS'::*;
    private import 'TRK-SC'::*;

    part kettle {
        part element : Heater;
    }

    satisfy 'SYS-001' by kettle.element;
    satisfy 'SYS-001' by kettle;
}
