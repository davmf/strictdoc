package 'SC-001' {
    private import 'TRK-SYS'::*;

    part kettle {
        part element;
    }

    satisfy 'SYS-001' by kettle.element;
    satisfy 'SYS-001' by kettle;
}
