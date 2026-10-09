# Driver behaviour on Indian city roads

This defines how drivers behave in the Terascope AI (CityRehearsal) traffic simulation. It was built using TomTom
junction data and the team's local knowledge of those roads. The rules are written to apply to any comparable Indian
city arterial.

Every behaviour carries a source label:

- **measured**: TomTom data;
- **estimated**: tuned until the simulation matched TomTom;
- **assumed**: local knowledge, not yet checked against data.

## 1. The road

- Traffic keeps left. A left turn is the short turn; a right turn crosses oncoming traffic. [assumed]
- Drivers fit more vehicles across a road than its painted lanes suggest. Real capacity is 1.3–1.4 times the marked
  lanes, so the model uses marked lanes × 1.35. [assumed]
- One 3.2 m lane holds, side by side: three two-wheelers, or one auto and one two-wheeler, or one car, bus or truck. [assumed]
- Where there is a flyover, most through traffic takes it: about 81% of through traffic in the one direction measured. [measured]

## 2. Who is on the road

| Type | Share | Length × width | Top speed | Pull-away / braking |
|---|---|---|---|---|
| two_wheeler | 47%, 30% of them fast riders | 2.0 × 0.8 m | 60 km/h; fast riders 80 | 2.5 m/s² (fast 3.0) / 4.5 m/s² (fast 5.0) |
| auto | 19%, half of them fast drivers | 2.6 × 1.5 m | 50 km/h; fast drivers 60 | 1.2 m/s² (fast 1.4) / 4.0 m/s² |
| car | 27% | 4.3 × 1.8 m | 80 km/h | 2.6 m/s² / 4.5 m/s² |
| bus | 4% | 12.0 × 2.5 m | 60 km/h | 1.0 m/s² / 4.0 m/s² |
| truck | 3% | 7.5 × 2.5 m | 60 km/h | 1.0 m/s² / 4.0 m/s² |

- The shares and sizes are assumed. [assumed]
- Fast riders are the aggressive group: half of two-wheeler riders and 30% of auto drivers. They speed, weave and break
  signal rules more than anyone else (sections 3, 4 and 7). [assumed]
  (Note: the table says 30% of two-wheelers and half of autos; this sentence says the reverse. To be confirmed by the team;
  the implementation follows the table.)
- Buses and trucks pull away slowly, so the queue behind one at a signal clears slowly. [assumed]

## 3. Speed and following

- Speeding: fast two-wheeler riders go about 1.25 times the speed limit (spread 1.05–1.5), fast auto drivers about 1.2
  times (1.0–1.4). Everyone else drives near the limit (0.8–1.2 times). [assumed]
- Drivers follow closer than standard traffic models assume. Gap kept when stopped / reaction time: two-wheeler 0.8 m /
  0.8 s (fast riders 0.6 m / 0.6 s), auto 1.2 m / 0.9 s (fast 1.0 m / 0.8 s), car 2.0 m / 1.0 s, bus and truck 2.5 m / 1.0 s. [assumed]
- Speeds are uneven: drivers drift above and below their chosen speed (imperfection 0.5 on a 0–1 scale, fast riders 0.6). [assumed]

## 4. Position in the lane, filtering and weaving

- Two-wheelers and autos ride anywhere across the lane; cars, buses and trucks keep to the lane centre. [assumed]
- Side clearance kept from the next vehicle: two-wheeler 0.25 m, auto 0.4 m, car 0.8 m, bus and truck 0.6 m. [assumed]
- Sideways movement: two-wheelers drift sideways at up to 1.5 m/s (fast riders 2.0 m/s), autos up to 1.0 m/s (fast
  drivers 1.3 m/s). [assumed]
- Filtering: two-wheelers and autos overtake inside a lane and squeeze between cars, including through queues stopped
  at a red, so they gather at the front of the queue. Two-wheelers and autos side by side within one lane, or across
  lane lines, is normal. [assumed]
- Weaving: fast riders change lanes for small speed gains, push into gaps others leave, accept small gaps, and get more
  aggressive the longer they are held up. Ordinary riders push in less. [assumed]

## 5. Signals

- Free left: left-turners go in every phase, giving way to traffic that has green. [assumed]
- Police control: traffic police let the longer queue go, so a green stretches from 10 s up to twice its planned length.
  Amber lasts 4 s. [assumed]
- At big junctions with three or more busy approaches, one approach goes at a time, so right-turners never face oncoming
  traffic. Cycle about 150 s. [assumed]
- Where a main road crosses a smaller road, the main road runs both ways together. Its right-turners wait in the median
  lane for a gap in oncoming traffic, then get a short protected right-turn phase (12 s, stretching from 6 to 25 s),
  then the side road goes. Without that phase, right-turners facing about 3,300 vehicles/h of oncoming traffic never
  found a gap and froze the median lane for 5–12 minutes. The main road keeps at least 65% of the green; cycle 100–150 s. [estimated]
- Green is shared in proportion to each approach's traffic per lane. [assumed]
- U-turns at signals are common: on one measured approach 24% of traffic turned back [measured]. U-turners don't stop
  and wait in the middle of the junction; they swing round when they can [assumed].
- Side roads at signals have no lane discipline when turning: any lane makes any turn, and traffic fans out across the
  approach. [assumed]

## 6. Giving way and side streets

- A driver who must give way noses out in front of a vehicle that has right of way once that vehicle is crawling below
  1.5 m/s (about 5 km/h), with a 30% chance every half-second. [assumed]
- After 30 s of waiting, drivers accept much smaller gaps. [assumed]
- A vehicle stuck inside a junction for more than 15 s stops holding others up; they move through past it. [assumed]
- Small residential streets on a divided road are left in, left out: vehicles turn left into or out of them and don't
  cross the median. U-turns through median gaps between junctions are not covered here. [assumed]
- Drivers coming out of side streets force their way into the main road whenever it moves slower than 5 m/s (18 km/h),
  with a 50% chance every half-second. Without this, a street beside a queue never got a gap. Beside a long queue they
  can still wait several minutes. [estimated]

## 7. Red lights and blocked junctions

The values provided in this are starting points to calibrate, for example against TomTom's stops and queues.

### Creeping past the stop line

- During a red, filtering two-wheelers and autos don't stop at the line. They stop past it, on the pedestrian crossing:
  fast two-wheeler riders up to 3 m past, other two-wheelers and fast autos up to 2 m, other autos and cars up to 1 m.
  Buses and trucks stop at the line. [assumed]
- Whenever there is room ahead they inch forward at walking pace (up to 1 m/s). They stop at the edge of the crossing
  traffic's path, never inside it. [assumed]
- In the last 3 s of red the front of the queue rolls forward at walking pace, so it crosses the line as the green comes on. [assumed]

### Going through on amber and early red

- Nobody brakes for amber: any vehicle that reaches the line during the 4 s amber goes through. [assumed]
- Just after the red, drivers already close to the line keep going: fast riders up to 2 s into the red, other
  two-wheelers, autos and cars up to 1 s. Buses and trucks stop. Red-runners keep their speed, up to 40 km/h. [assumed]
- With creeping, this means the first second or two of a green is often shared with the last red-runners from the
  previous phase. [assumed]

### Blocking the box

- On green, drivers enter the junction even when the road beyond it is full, and stop inside, in the path of the next
  phase's traffic. Two-wheelers and autos do it at once; cars after waiting 5 s; buses and trucks after 10 s. [assumed]
- Cross traffic works its way around them. Once a blocker has stood for 30 s, others move past it as if it weren't
  there (section 6), which stops box-blocking turning into gridlock. [assumed]

### Starting values per vehicle type

| Behaviour | two_wheeler, fast | two_wheeler | auto, fast | auto | car | bus, truck |
|---|---|---|---|---|---|---|
| Stops this far past the line on red | 3 m | 2 m | 2 m | 1 m | 1 m | 0 m |
| Goes through amber for its whole length | 4 s | 4 s | 4 s | 4 s | 4 s | 4 s |
| Keeps going after the red starts | 2 s | 1 s | 2 s | 1 s | 1 s | stops |
| Speed while running a red | up to 40 km/h | up to 40 km/h | up to 40 km/h | up to 40 km/h | up to 40 km/h | — |
| Enters a full junction after waiting | 0 s | 0 s | 0 s | 0 s | 5 s | 10 s |

In SUMO terms: amber is jmDriveAfterYellowTime, red-running jmDriveAfterRedTime with jmDriveRedSpeed (11.1 m/s),
box-blocking jmIgnoreKeepClearTime, and the 15 s rule --ignore-junction-blocker 15. SUMO can't stop a vehicle past the
line (jmStoplineGap must be 0 or more), so jmStoplineGap 0 gets it to the line and the overshoot has to come from a
custom model or the viewer.
