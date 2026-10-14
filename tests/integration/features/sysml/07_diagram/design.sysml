package 'Diagram design' {
    doc /*
     * Design text below the diagram.
     */

    part def Heater;

    part def Station {
        part heater : Heater;
        satisfy 'DGM-REQ-1' by heater;
    }
}
