package 'SYS-001' {
    private import ScalarValues::*;
    private import 'TRK-STK'::*;

    requirement <'SYS-001'> 'Boil time' {
        doc /*
         * The kettle shall boil 1 litre in at most 180 s.
         */
        attribute boilTime : Real;
    }

    dependency from 'SYS-001' to 'STK-001';
}
